#!/usr/bin/env python3
"""Collect PPO-style rollouts from the current policy and local executor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from simple_openhands.rl import CodePolicy, LocalCodeSandboxEnv, compute_batch_advantages, load_jsonl


REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Collect prompt -> generation -> reward rollouts before PPO updates."
    )
    parser.add_argument(
        "--input",
        default="data/final/rl_train.jsonl",
        help="RL-format JSONL file.",
    )
    parser.add_argument(
        "--base-model-path",
        required=True,
        help="Path to the base model directory.",
    )
    parser.add_argument(
        "--adapter-path",
        default=None,
        help="Optional SFT adapter path for initializing the policy.",
    )
    parser.add_argument(
        "--out-dir",
        default="outputs/ppo_rollouts",
        help="Directory to write rollout batches.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional sample cap.",
    )
    parser.add_argument(
        "--max-new-tokens",
        type=int,
        default=256,
        help="Maximum generated tokens per sample.",
    )
    parser.add_argument(
        "--prompt-template",
        default="### Problem:\n{prompt}\n\n### Solution:\n",
        help="Prompt template for inference.",
    )
    parser.add_argument(
        "--trust-remote-code",
        action="store_true",
        help="Pass trust_remote_code=True when loading the model.",
    )
    parser.add_argument(
        "--reward-mode",
        choices=("v2", "v3", "v3b"),
        default="v2",
        help="Reward function version used for rollout collection.",
    )
    return parser.parse_args()


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def summarize(rollouts: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rollouts)
    full_pass = sum(1 for item in rollouts if item["passed"])
    average_reward = 0.0 if total == 0 else round(sum(item["reward"] for item in rollouts) / total, 4)
    average_advantage = (
        0.0 if total == 0 else round(sum(item["advantage"] for item in rollouts) / total, 6)
    )
    return {
        "total_rollouts": total,
        "pass_at_1": 0.0 if total == 0 else round(full_pass / total, 4),
        "average_reward": average_reward,
        "average_advantage": average_advantage,
    }


def main() -> int:
    args = parse_args()
    input_path = (REPO_ROOT / args.input).resolve()
    out_dir = (REPO_ROOT / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    records = load_jsonl(input_path)
    if args.limit is not None:
        records = records[: args.limit]

    env = LocalCodeSandboxEnv(records, reward_mode=args.reward_mode)
    policy = CodePolicy(
        base_model_path=args.base_model_path,
        trust_remote_code=args.trust_remote_code,
        adapter_path=args.adapter_path,
        prompt_template=args.prompt_template,
    )

    rollouts: list[dict[str, Any]] = []
    rewards: list[float] = []
    for index in range(len(records)):
        observation = env.reset(index)
        generation = policy.generate(
            prompt=str(observation["prompt"]),
            max_new_tokens=args.max_new_tokens,
        )
        _, reward, done, info = env.step(generation["response_text"])
        if not done:
            raise RuntimeError("This minimal environment expects single-step episodes.")

        old_logprob = policy.response_logprob(
            prompt_text=generation["prompt_text"],
            response_text=generation["response_text"],
        )
        rewards.append(reward)
        rollouts.append(
            {
                "task_id": observation["task_id"],
                "prompt": observation["prompt"],
                "entry_point": observation["entry_point"],
                "generated_solution": generation["response_text"],
                "response_token_count": generation["response_token_count"],
                "reward": reward,
                "old_logprob": round(old_logprob, 6),
                **info,
            }
        )
        if (index + 1) % 10 == 0 or (index + 1) == len(records):
            print(f"Collected {index + 1}/{len(records)} rollouts...")

    policy.unload()

    advantages = compute_batch_advantages(rewards)
    for rollout, advantage in zip(rollouts, advantages, strict=True):
        rollout["advantage"] = advantage
        rollout["return"] = rollout["reward"]

    summary = {
        "input_file": str(input_path),
        "base_model_path": args.base_model_path,
        "adapter_path": args.adapter_path,
        "reward_mode": args.reward_mode,
        **summarize(rollouts),
        "note": "This script completes rollout collection, local execution, reward computation, and advantage preprocessing for the next PPO update step.",
    }

    write_jsonl(out_dir / "rollouts.jsonl", rollouts)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
