#!/usr/bin/env python3
"""Validate dataset samples inside the running Simple OpenHands runtime."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
SUCCESS_MARKER = "__RUNTIME_VALIDATION_OK__"


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


def build_runtime_code(record: dict[str, Any]) -> str:
    solution = record["canonical_solution"].replace("\r\n", "\n").rstrip()
    tests = record["test_code"].replace("\r\n", "\n").rstrip()
    solution_literal = repr(solution + "\n")
    tests_literal = repr(tests + "\n")
    return (
        "namespace = {'__builtins__': __builtins__}\n"
        f"exec({solution_literal}, namespace, namespace)\n"
        f"exec({tests_literal}, namespace, namespace)\n"
        f"print('{SUCCESS_MARKER}')\n"
    )


def validate_record(
    record: dict[str, Any], runtime_url: str, timeout_seconds: float
) -> dict[str, Any]:
    payload = {
        "action": {
            "action": "run_ipython",
            "args": {
                "code": build_runtime_code(record),
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
            "task_id": record["task_id"],
            "source": record["source"],
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
        "task_id": record["task_id"],
        "source": record["source"],
        "passed": passed,
        "status_code": response.status_code,
        "error_type": error_type,
        "content": content,
        "raw_response": data,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate RL dataset samples inside the running runtime."
    )
    parser.add_argument(
        "--input",
        default="data/final/rl_valid.jsonl",
        help="Path to RL-format JSONL file.",
    )
    parser.add_argument(
        "--out-dir",
        default="data/runtime_validated",
        help="Directory to write validation outputs.",
    )
    parser.add_argument(
        "--url",
        default="http://127.0.0.1:8002",
        help="Runtime base URL.",
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
        help="Optional sample limit for smoke tests.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = (REPO_ROOT / args.input).resolve()
    out_dir = (REPO_ROOT / args.out_dir).resolve()

    records = load_jsonl(input_path)
    if args.limit is not None:
        records = records[: args.limit]

    passed_records: list[dict[str, Any]] = []
    failed_records: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []

    for index, record in enumerate(records, start=1):
        result = validate_record(record, args.url, args.timeout)
        results.append(result)
        if result["passed"]:
            passed_records.append(record)
        else:
            failed_records.append(
                {
                    "task_id": record["task_id"],
                    "source": record["source"],
                    "prompt": record["prompt"],
                    "entry_point": record["entry_point"],
                    "error_type": result["error_type"],
                    "status_code": result["status_code"],
                    "content": result["content"],
                    "raw_response": result["raw_response"],
                }
            )

        if index % 10 == 0:
            print(f"Validated {index}/{len(records)} runtime samples...")

    write_jsonl(out_dir / "passed.jsonl", passed_records)
    write_jsonl(out_dir / "failed.jsonl", failed_records)
    write_jsonl(out_dir / "results.jsonl", results)

    summary = {
        "input_records": len(records),
        "passed_records": len(passed_records),
        "failed_records": len(failed_records),
        "pass_rate": 0.0 if not records else round(len(passed_records) / len(records), 4),
        "runtime_url": args.url,
        "out_dir": str(out_dir),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
