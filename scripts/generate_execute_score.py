#!/usr/bin/env python3
"""Generate code, execute tests, and score samples for PPO warm-up."""

from __future__ import annotations

import argparse
import gc
import json
import traceback
from pathlib import Path
from typing import Any

import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from simple_openhands.rl.bridge import (
    align_entry_point,
    clean_generated_solution,
    compute_reward,
    execute_test_code,
    uses_humaneval_check,
)

try:
    from peft import PeftModel
except ImportError:  # pragma: no cover
    PeftModel = None


REPO_ROOT = Path(__file__).resolve().parent.parent


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate code and compute execution rewards on RL-format data."
    )
    parser.add_argument(
        "--input",
        default="data/final/rl_train.jsonl",
        help="RL-format JSONL file to score.",
    )
    parser.add_argument(
        "--base-model-path",
        required=True,
        help="Path to the base model directory.",
    )
    parser.add_argument(
        "--adapter-path",
        default=None,
        help="Optional LoRA adapter path. Omit to score the base model.",
    )
    parser.add_argument(
        "--out-dir",
        default="outputs/ppo_bridge",
        help="Directory to write scored rollouts.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional sample limit for quick runs.",
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
        help="Prompt template used for inference.",
    )
    parser.add_argument(
        "--trust-remote-code",
        action="store_true",
        help="Pass trust_remote_code=True when loading model/tokenizer.",
    )
    parser.add_argument(
        "--reward-mode",
        choices=("v2", "v3", "v3b"),
        default="v2",
        help="Reward function version used for average_reward.",
    )
    return parser.parse_args()


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as fh:
        for line_no, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSONL at {path}:{line_no}: {exc}") from exc
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def infer_dtype() -> torch.dtype | None:
    if torch.cuda.is_available():
        return torch.bfloat16
    return None


def load_model_and_tokenizer(
    base_model_path: str, trust_remote_code: bool, adapter_path: str | None = None
) -> tuple[Any, Any]:
    tokenizer = AutoTokenizer.from_pretrained(
        base_model_path,
        trust_remote_code=trust_remote_code,
    )
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    model = AutoModelForCausalLM.from_pretrained(
        base_model_path,
        trust_remote_code=trust_remote_code,
        dtype=infer_dtype(),
        device_map="auto" if torch.cuda.is_available() else None,
    )

    if adapter_path is not None:
        if PeftModel is None:
            raise ImportError("peft is required to load the SFT adapter.")
        model = PeftModel.from_pretrained(model, adapter_path)

    model.eval()
    return model, tokenizer


def unload_model(model: Any, tokenizer: Any) -> None:
    del model
    del tokenizer
    gc.collect()
    if torch.cuda.is_available():
        torch.cuda.empty_cache()


def generate_solution(
    model: Any,
    tokenizer: Any,
    prompt: str,
    prompt_template: str,
    max_new_tokens: int,
) -> str:
    prompt_text = prompt_template.format(prompt=prompt)
    inputs = tokenizer(prompt_text, return_tensors="pt")
    if hasattr(model, "device"):
        inputs = {key: value.to(model.device) for key, value in inputs.items()}

    with torch.no_grad():
        outputs = model.generate(
            **inputs,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
        )

    generated_text = tokenizer.decode(outputs[0], skip_special_tokens=True)
    if generated_text.startswith(prompt_text):
        return generated_text[len(prompt_text) :].strip()
    return generated_text.strip()


def extract_asserts(test_code: str) -> list[str]:
    lines = [line.strip() for line in test_code.replace("\r\n", "\n").split("\n")]
    return [line for line in lines if line.startswith("assert ")]


def score_solution(
    generated_solution: str,
    record: dict[str, Any],
    reward_mode: str = "v2",
) -> dict[str, Any]:
    namespace: dict[str, Any] = {"__builtins__": __builtins__}
    cleaned_solution = clean_generated_solution(generated_solution)
    aligned_solution = align_entry_point(
        generated_solution=cleaned_solution,
        entry_point=str(record["entry_point"]),
    )

    try:
        exec(aligned_solution + "\n", namespace, namespace)
    except Exception:
        test_code = str(record["test_code"])
        return {
            "reward": 0.0,
            "passed": False,
            "passed_tests": 0,
            "total_tests": 1 if uses_humaneval_check(test_code) else len(extract_asserts(test_code)),
            "error_type": "generation_execution_error",
            "content": traceback.format_exc(),
            "reward_components": {
                "executable": 0.0,
                "entry_point": 0.0,
                "ast": 0.0,
                "signature": 0.0,
                "test_pass_ratio": 0.0,
                "full_pass": 0.0,
            },
        }

    passed_tests, total_tests, failure_trace = execute_test_code(
        namespace=namespace,
        record=record,
    )
    reward, reward_components = compute_reward(
        record=record,
        namespace=namespace,
        cleaned_solution=cleaned_solution,
        aligned_solution=aligned_solution,
        passed_tests=passed_tests,
        total_tests=total_tests,
        execution_ok=True,
        reward_mode=reward_mode,
    )
    passed = passed_tests == total_tests

    return {
        "reward": reward,
        "passed": passed,
        "passed_tests": passed_tests,
        "total_tests": total_tests,
        "error_type": None if passed else "partial_or_failed_tests",
        "content": "" if passed else (failure_trace or ""),
        "reward_components": reward_components,
    }


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(records)
    full_pass = sum(1 for item in records if item["passed"])
    avg_reward = 0.0 if total == 0 else round(sum(item["reward"] for item in records) / total, 4)
    syntax_fail = sum(1 for item in records if item["error_type"] == "generation_execution_error")
    return {
        "total_records": total,
        "full_pass_records": full_pass,
        "pass_at_1": 0.0 if total == 0 else round(full_pass / total, 4),
        "average_reward": avg_reward,
        "generation_execution_failures": syntax_fail,
    }


def main() -> int:
    args = parse_args()
    input_path = (REPO_ROOT / args.input).resolve()
    out_dir = (REPO_ROOT / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    records = load_jsonl(input_path)
    if args.limit is not None:
        records = records[: args.limit]

    model, tokenizer = load_model_and_tokenizer(
        base_model_path=args.base_model_path,
        trust_remote_code=args.trust_remote_code,
        adapter_path=args.adapter_path,
    )

    scored_records: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        generated_solution = generate_solution(
            model=model,
            tokenizer=tokenizer,
            prompt=str(record["prompt"]),
            prompt_template=args.prompt_template,
            max_new_tokens=args.max_new_tokens,
        )
        score = score_solution(
            generated_solution=generated_solution,
            record=record,
            reward_mode=args.reward_mode,
        )
        scored_records.append(
            {
                "task_id": record["task_id"],
                "source": record["source"],
                "prompt": record["prompt"],
                "entry_point": record["entry_point"],
                "generated_solution": generated_solution,
                **score,
            }
        )
        if index % 10 == 0 or index == len(records):
            print(f"Scored {index}/{len(records)} samples...")

    unload_model(model, tokenizer)

    summary = {
        "input_file": str(input_path),
        "base_model_path": args.base_model_path,
        "adapter_path": args.adapter_path,
        "reward_mode": args.reward_mode,
        **summarize(scored_records),
    }
    write_jsonl(out_dir / "scored_rollouts.jsonl", scored_records)
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
