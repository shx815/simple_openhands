#!/usr/bin/env python3
"""Validate normalized code-generation datasets by executing solutions and tests."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import uuid
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


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


def build_program(record: dict[str, Any]) -> str:
    solution = record["canonical_solution"].replace("\r\n", "\n").rstrip()
    tests = record["test_code"].replace("\r\n", "\n").rstrip()
    return f"{solution}\n\n{tests}\n"


def validate_record(
    record: dict[str, Any],
    python_executable: str,
    timeout_seconds: float,
    temp_root: Path,
) -> dict[str, Any]:
    program = build_program(record)
    sample_dir = temp_root / f"sample_{uuid.uuid4().hex}"
    sample_dir.mkdir(parents=True, exist_ok=True)
    program_path = sample_dir / "validate_sample.py"
    try:
        program_path.write_text(program, encoding="utf-8")

        try:
            result = subprocess.run(
                [python_executable, str(program_path)],
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=timeout_seconds,
            )
            passed = result.returncode == 0
            return {
                "task_id": record["task_id"],
                "source": record["source"],
                "passed": passed,
                "returncode": result.returncode,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "error_type": None if passed else "runtime_error",
            }
        except subprocess.TimeoutExpired as exc:
            return {
                "task_id": record["task_id"],
                "source": record["source"],
                "passed": False,
                "returncode": None,
                "stdout": exc.stdout or "",
                "stderr": exc.stderr or "",
                "error_type": "timeout",
            }
    finally:
        shutil.rmtree(sample_dir, ignore_errors=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate master.jsonl by executing canonical solutions against tests."
    )
    parser.add_argument(
        "--input",
        default="data/processed/master.jsonl",
        help="Path to normalized master JSONL.",
    )
    parser.add_argument(
        "--out-dir",
        default="data/validated",
        help="Directory to write validation outputs.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable used to run validation programs.",
    )
    parser.add_argument(
        "--timeout",
        type=float,
        default=5.0,
        help="Per-sample timeout in seconds.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Optional sample limit for quick smoke tests.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = (REPO_ROOT / args.input).resolve()
    out_dir = (REPO_ROOT / args.out_dir).resolve()
    temp_root = out_dir / "tmp"
    temp_root.mkdir(parents=True, exist_ok=True)

    records = load_jsonl(input_path)
    if args.limit is not None:
        records = records[: args.limit]

    passed_records: list[dict[str, Any]] = []
    failed_records: list[dict[str, Any]] = []
    validation_results: list[dict[str, Any]] = []

    for index, record in enumerate(records, start=1):
        result = validate_record(record, args.python, args.timeout, temp_root)
        validation_results.append(result)
        if result["passed"]:
            passed_records.append(record)
        else:
            failed_record = {
                "task_id": record["task_id"],
                "source": record["source"],
                "prompt": record["prompt"],
                "entry_point": record["entry_point"],
                "error_type": result["error_type"],
                "returncode": result["returncode"],
                "stdout": result["stdout"],
                "stderr": result["stderr"],
            }
            failed_records.append(failed_record)

        if index % 50 == 0:
            print(f"Validated {index}/{len(records)} samples...")

    write_jsonl(out_dir / "passed.jsonl", passed_records)
    write_jsonl(out_dir / "failed.jsonl", failed_records)
    write_jsonl(out_dir / "results.jsonl", validation_results)

    summary = {
        "input_records": len(records),
        "passed_records": len(passed_records),
        "failed_records": len(failed_records),
        "pass_rate": 0.0 if not records else round(len(passed_records) / len(records), 4),
        "out_dir": str(out_dir),
    }
    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    shutil.rmtree(temp_root, ignore_errors=True)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
