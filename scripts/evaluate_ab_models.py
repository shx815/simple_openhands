#!/usr/bin/env python3
"""A/B evaluate base vs SFT model on RL-style code generation tasks."""

from __future__ import annotations

import argparse
import gc
import json
import traceback
from pathlib import Path
from typing import Any

import requests
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

try:
    from peft import PeftModel
except ImportError:  # pragma: no cover
    PeftModel = None


REPO_ROOT = Path(__file__).resolve().parent.parent
SUCCESS_MARKER = "__AB_EVAL_OK__"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare base and SFT models with runtime-backed Pass@1 evaluation."
    )
    parser.add_argument(
        "--input",
        default="data/final/rl_valid.jsonl",
        help="RL-format JSONL evaluation file.",
    )
    parser.add_argument(
        "--base-model-path",
        required=True,
        help="Path to the base model directory.",
    )
    parser.add_argument(
        "--adapter-path",
        required=True,
        help="Path to the trained LoRA adapter directory.",
    )
    parser.add_argument(
        "--out-dir",
        default="outputs/ab_eval",
        help="Directory to write comparison outputs.",
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8002",
        help="Runtime base URL.",
    )
    parser.add_argument(
        "--execution-mode",
        choices=["local", "runtime"],
        default="local",
        help="How to execute generated code against tests.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Per-request timeout in seconds.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional sample limit for quick checks.",
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
        help="Pass trust_remote_code=True when loading models/tokenizer.",
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


def build_runtime_code(generated_solution: str, test_code: str) -> str:
    solution = generated_solution.replace("\r\n", "\n").rstrip() + "\n"
    tests = test_code.replace("\r\n", "\n").rstrip() + "\n"
    return (
        "namespace = {'__builtins__': __builtins__}\n"
        f"exec({solution!r}, namespace, namespace)\n"
        f"exec({tests!r}, namespace, namespace)\n"
        f"print('{SUCCESS_MARKER}')\n"
    )


def run_in_runtime(
    generated_solution: str,
    record: dict[str, Any],
    runtime_url: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    payload = {
        "action": {
            "action": "run_ipython",
            "args": {
                "code": build_runtime_code(generated_solution, str(record["test_code"])),
            },
        }
    }

    try:
        response = requests.post(
            runtime_url.rstrip("/") + "/execute_action",
            json=payload,
            timeout=timeout_seconds,
        )
    except requests.RequestException as exc:
        return {
            "passed": False,
            "status_code": None,
            "error_type": "request_error",
            "content": str(exc),
            "raw_response": None,
        }

    try:
        data = response.json()
    except ValueError:
        data = {"raw_text": response.text}

    content = ""
    if isinstance(data, dict):
        content = str(data.get("content", ""))

    passed = response.ok and SUCCESS_MARKER in content
    error_type = None
    if not response.ok:
        error_type = "http_error"
    elif SUCCESS_MARKER not in content:
        error_type = "runtime_assertion_or_execution_error"

    return {
        "passed": passed,
        "status_code": response.status_code,
        "error_type": error_type,
        "content": content,
        "raw_response": data,
    }


def run_locally(generated_solution: str, record: dict[str, Any]) -> dict[str, Any]:
    namespace: dict[str, Any] = {"__builtins__": __builtins__}
    try:
        exec(generated_solution.replace("\r\n", "\n").rstrip() + "\n", namespace, namespace)
        exec(str(record["test_code"]).replace("\r\n", "\n").rstrip() + "\n", namespace, namespace)
    except Exception:
        return {
            "passed": False,
            "status_code": None,
            "error_type": "local_execution_error",
            "content": traceback.format_exc(),
            "raw_response": None,
        }

    return {
        "passed": True,
        "status_code": None,
        "error_type": None,
        "content": SUCCESS_MARKER,
        "raw_response": None,
    }


def evaluate_model(
    model_label: str,
    base_model_path: str,
    adapter_path: str | None,
    records: list[dict[str, Any]],
    args: argparse.Namespace,
) -> list[dict[str, Any]]:
    print(f"Loading {model_label} model...")
    model, tokenizer = load_model_and_tokenizer(
        base_model_path=base_model_path,
        trust_remote_code=args.trust_remote_code,
        adapter_path=adapter_path,
    )

    results: list[dict[str, Any]] = []
    for index, record in enumerate(records, start=1):
        generated_solution = generate_solution(
            model=model,
            tokenizer=tokenizer,
            prompt=str(record["prompt"]),
            prompt_template=args.prompt_template,
            max_new_tokens=args.max_new_tokens,
        )
        if args.execution_mode == "runtime":
            execution_result = run_in_runtime(
                generated_solution=generated_solution,
                record=record,
                runtime_url=args.url,
                timeout_seconds=args.timeout,
            )
        else:
            execution_result = run_locally(
                generated_solution=generated_solution,
                record=record,
            )
        results.append(
            {
                "task_id": record["task_id"],
                "source": record["source"],
                "entry_point": record["entry_point"],
                "prompt": record["prompt"],
                "generated_solution": generated_solution,
                **execution_result,
            }
        )
        if index % 10 == 0 or index == len(records):
            print(f"{model_label}: evaluated {index}/{len(records)} samples...")

    unload_model(model, tokenizer)
    return results


def summarize_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    passed_records = sum(1 for item in results if item["passed"])
    total_records = len(results)
    return {
        "total_records": total_records,
        "passed_records": passed_records,
        "failed_records": total_records - passed_records,
        "pass_at_1": 0.0 if total_records == 0 else round(passed_records / total_records, 4),
    }


def build_comparison(
    base_results: list[dict[str, Any]], sft_results: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    base_by_task = {item["task_id"]: item for item in base_results}
    sft_by_task = {item["task_id"]: item for item in sft_results}
    comparison: list[dict[str, Any]] = []

    for task_id in base_by_task:
        base_item = base_by_task[task_id]
        sft_item = sft_by_task[task_id]
        comparison.append(
            {
                "task_id": task_id,
                "source": base_item["source"],
                "base_passed": base_item["passed"],
                "sft_passed": sft_item["passed"],
                "improved": (not base_item["passed"]) and sft_item["passed"],
                "regressed": base_item["passed"] and (not sft_item["passed"]),
                "base_error_type": base_item["error_type"],
                "sft_error_type": sft_item["error_type"],
            }
        )
    return comparison


def main() -> int:
    args = parse_args()
    input_path = (REPO_ROOT / args.input).resolve()
    out_dir = (REPO_ROOT / args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    records = load_jsonl(input_path)
    if args.limit is not None:
        records = records[: args.limit]

    base_results = evaluate_model(
        model_label="base",
        base_model_path=args.base_model_path,
        adapter_path=None,
        records=records,
        args=args,
    )
    sft_results = evaluate_model(
        model_label="sft",
        base_model_path=args.base_model_path,
        adapter_path=args.adapter_path,
        records=records,
        args=args,
    )

    comparison = build_comparison(base_results, sft_results)
    base_summary = summarize_results(base_results)
    sft_summary = summarize_results(sft_results)
    overall_summary = {
        "input_file": str(input_path),
        "execution_mode": args.execution_mode,
        "runtime_url": args.url if args.execution_mode == "runtime" else None,
        "base_model_path": args.base_model_path,
        "adapter_path": args.adapter_path,
        "base_summary": base_summary,
        "sft_summary": sft_summary,
        "absolute_pass_at_1_gain": round(
            sft_summary["pass_at_1"] - base_summary["pass_at_1"], 4
        ),
        "improved_cases": sum(1 for item in comparison if item["improved"]),
        "regressed_cases": sum(1 for item in comparison if item["regressed"]),
        "unchanged_cases": sum(
            1 for item in comparison if not item["improved"] and not item["regressed"]
        ),
    }

    write_jsonl(out_dir / "base_results.jsonl", base_results)
    write_jsonl(out_dir / "sft_results.jsonl", sft_results)
    write_jsonl(out_dir / "comparison.jsonl", comparison)
    (out_dir / "summary.json").write_text(
        json.dumps(overall_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(overall_summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
