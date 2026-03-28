#!/usr/bin/env python3
"""Minimal PPO policy update over collected code-generation rollouts."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

import torch
from torch import nn
from torch.optim import AdamW

from simple_openhands.rl import CodePolicy, ScalarValueHead, compute_single_step_gae, load_jsonl


REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a minimal PPO clipped-policy update on saved rollouts."
    )
    parser.add_argument(
        "--input",
        default="outputs/ppo_rollouts_valid_smoke_v2/rollouts.jsonl",
        help="Path to rollout JSONL file.",
    )
    parser.add_argument(
        "--base-model-path",
        required=True,
        help="Path to the base model directory.",
    )
    parser.add_argument(
        "--adapter-path",
        required=True,
        help="Path to the trainable LoRA adapter used as the current policy.",
    )
    parser.add_argument(
        "--out-dir",
        default="outputs/ppo_policy_update",
        help="Directory to save the updated adapter and metrics.",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=1,
        help="Number of PPO passes over the rollout batch.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=4,
        help="Mini-batch size for PPO updates.",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=1e-5,
        help="Optimizer learning rate.",
    )
    parser.add_argument(
        "--clip-eps",
        type=float,
        default=0.2,
        help="PPO clipping epsilon.",
    )
    parser.add_argument(
        "--max-grad-norm",
        type=float,
        default=1.0,
        help="Gradient clipping norm.",
    )
    parser.add_argument(
        "--value-coef",
        type=float,
        default=0.5,
        help="Weight for the value loss term.",
    )
    parser.add_argument(
        "--kl-coef",
        type=float,
        default=0.02,
        help="Weight for the KL penalty against the base/reference policy.",
    )
    parser.add_argument(
        "--value-head-dropout",
        type=float,
        default=0.0,
        help="Dropout used in the scalar value head.",
    )
    parser.add_argument(
        "--gamma",
        type=float,
        default=1.0,
        help="Reward discount factor. Single-step episodes keep the default at 1.0.",
    )
    parser.add_argument(
        "--gae-lambda",
        type=float,
        default=1.0,
        help="GAE lambda. Single-step episodes keep the default at 1.0.",
    )
    parser.add_argument(
        "--prompt-template",
        default="### Problem:\n{prompt}\n\n### Solution:\n",
        help="Prompt template used during rollout collection.",
    )
    parser.add_argument(
        "--trust-remote-code",
        action="store_true",
        help="Pass trust_remote_code=True when loading the model.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for mini-batch ordering.",
    )
    return parser.parse_args()


def batched(records: list[dict[str, Any]], batch_size: int) -> list[list[dict[str, Any]]]:
    return [records[index : index + batch_size] for index in range(0, len(records), batch_size)]


def compute_response_logprob_tensor(
    policy: CodePolicy, prompt_text: str, response_text: str
) -> torch.Tensor:
    logprob, _ = policy.response_stats(prompt_text=prompt_text, response_text=response_text)
    return logprob


def save_metrics(path: Path, metrics: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")


def infer_hidden_size(model: Any) -> int:
    hidden_size = getattr(model.config, "hidden_size", None)
    if hidden_size is None:
        raise ValueError("Unable to infer hidden_size from model config.")
    return int(hidden_size)


def main() -> int:
    args = parse_args()
    random.seed(args.seed)

    input_path = (REPO_ROOT / args.input).resolve()
    out_dir = (REPO_ROOT / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    rollouts = load_jsonl(input_path)
    if not rollouts:
        raise ValueError(f"No rollouts found in {input_path}")

    policy = CodePolicy(
        base_model_path=args.base_model_path,
        trust_remote_code=args.trust_remote_code,
        adapter_path=args.adapter_path,
        trainable_adapter=True,
        prompt_template=args.prompt_template,
    )
    policy.model.train()
    reference_policy = CodePolicy(
        base_model_path=args.base_model_path,
        trust_remote_code=args.trust_remote_code,
        adapter_path=None,
        trainable_adapter=False,
        prompt_template=args.prompt_template,
    )

    value_head = ScalarValueHead(
        hidden_size=infer_hidden_size(policy.model),
        dropout=args.value_head_dropout,
    ).to(policy.model.device)
    value_head.train()

    optimizer = AdamW(
        list(policy.model.parameters()) + list(value_head.parameters()),
        lr=args.learning_rate,
    )
    policy_loss_history: list[float] = []
    value_loss_history: list[float] = []
    kl_loss_history: list[float] = []
    total_loss_history: list[float] = []
    ratio_history: list[float] = []
    old_values: list[float] = []
    rollout_rewards = [float(sample["reward"]) for sample in rollouts]

    with torch.no_grad():
        for sample in rollouts:
            prompt_text = args.prompt_template.format(prompt=str(sample["prompt"]))
            response_text = str(sample["generated_solution"])
            _, pooled_hidden = policy.response_stats(prompt_text=prompt_text, response_text=response_text)
            value = value_head(pooled_hidden.unsqueeze(0)).squeeze(0)
            old_values.append(float(value.detach().cpu().item()))

    advantages, returns = compute_single_step_gae(
        rewards=rollout_rewards,
        values=old_values,
        gamma=args.gamma,
        lam=args.gae_lambda,
    )
    for rollout, advantage, ret, value in zip(
        rollouts, advantages, returns, old_values, strict=True
    ):
        rollout["advantage"] = round(float(advantage), 6)
        rollout["return"] = round(float(ret), 6)
        rollout["old_value"] = round(float(value), 6)

    for epoch in range(args.epochs):
        shuffled = rollouts.copy()
        random.shuffle(shuffled)

        for batch_index, batch in enumerate(batched(shuffled, args.batch_size), start=1):
            optimizer.zero_grad()
            batch_policy_losses: list[torch.Tensor] = []
            batch_value_losses: list[torch.Tensor] = []
            batch_kl_losses: list[torch.Tensor] = []
            batch_ratios: list[float] = []

            for sample in batch:
                prompt_text = args.prompt_template.format(prompt=str(sample["prompt"]))
                response_text = str(sample["generated_solution"])
                old_logprob = torch.tensor(
                    float(sample["old_logprob"]),
                    dtype=torch.float32,
                    device=policy.model.device,
                )
                advantage = torch.tensor(
                    float(sample["advantage"]),
                    dtype=torch.float32,
                    device=policy.model.device,
                )
                target_return = torch.tensor(
                    float(sample["return"]),
                    dtype=torch.float32,
                    device=policy.model.device,
                )

                current_logprob, pooled_hidden = policy.response_stats(
                    prompt_text=prompt_text,
                    response_text=response_text,
                )
                with torch.no_grad():
                    reference_logprob = compute_response_logprob_tensor(
                        policy=reference_policy,
                        prompt_text=prompt_text,
                        response_text=response_text,
                    )
                current_value = value_head(pooled_hidden.unsqueeze(0)).squeeze(0)
                ratio = torch.exp(current_logprob - old_logprob)
                unclipped = ratio * advantage
                clipped = torch.clamp(ratio, 1 - args.clip_eps, 1 + args.clip_eps) * advantage
                policy_loss = -torch.min(unclipped, clipped)
                value_loss = nn.functional.mse_loss(current_value, target_return)
                approx_kl = 0.5 * (current_logprob - reference_logprob).pow(2)

                batch_policy_losses.append(policy_loss)
                batch_value_losses.append(value_loss)
                batch_kl_losses.append(approx_kl)
                batch_ratios.append(float(ratio.detach().cpu().item()))

            policy_loss = torch.stack(batch_policy_losses).mean()
            value_loss = torch.stack(batch_value_losses).mean()
            kl_loss = torch.stack(batch_kl_losses).mean()
            loss = policy_loss + args.value_coef * value_loss + args.kl_coef * kl_loss
            loss.backward()
            torch.nn.utils.clip_grad_norm_(policy.model.parameters(), args.max_grad_norm)
            torch.nn.utils.clip_grad_norm_(value_head.parameters(), args.max_grad_norm)
            optimizer.step()

            policy_loss_history.append(float(policy_loss.detach().cpu().item()))
            value_loss_history.append(float(value_loss.detach().cpu().item()))
            kl_loss_history.append(float(kl_loss.detach().cpu().item()))
            total_loss_history.append(float(loss.detach().cpu().item()))
            ratio_history.extend(batch_ratios)
            print(
                f"epoch={epoch + 1} batch={batch_index} "
                f"total_loss={total_loss_history[-1]:.6f} "
                f"policy_loss={policy_loss_history[-1]:.6f} "
                f"value_loss={value_loss_history[-1]:.6f} "
                f"kl_loss={kl_loss_history[-1]:.6f} "
                f"avg_ratio={sum(batch_ratios) / len(batch_ratios):.6f}"
            )

    policy.model.save_pretrained(out_dir)
    policy.tokenizer.save_pretrained(out_dir)
    torch.save(value_head.state_dict(), out_dir / "value_head.pt")
    policy.unload()
    reference_policy.unload()

    summary = {
        "input_file": str(input_path),
        "base_model_path": args.base_model_path,
        "adapter_path": args.adapter_path,
        "output_dir": str(out_dir),
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "clip_eps": args.clip_eps,
        "value_coef": args.value_coef,
        "kl_coef": args.kl_coef,
        "gamma": args.gamma,
        "gae_lambda": args.gae_lambda,
        "num_rollouts": len(rollouts),
        "mean_total_loss": round(sum(total_loss_history) / len(total_loss_history), 6),
        "mean_policy_loss": round(sum(policy_loss_history) / len(policy_loss_history), 6),
        "mean_value_loss": round(sum(value_loss_history) / len(value_loss_history), 6),
        "mean_kl_loss": round(sum(kl_loss_history) / len(kl_loss_history), 6),
        "mean_ratio": round(sum(ratio_history) / len(ratio_history), 6),
        "mean_old_value": round(sum(old_values) / len(old_values), 6),
        "note": "This is a single-step PPO update with clipped policy loss, scalar value head, single-step GAE, and a KL penalty against the base policy. Multi-step trajectories and a full critic training loop are still pending.",
    }
    save_metrics(out_dir / "ppo_update_summary.json", summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
