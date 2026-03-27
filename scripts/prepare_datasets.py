#!/usr/bin/env python3
"""Normalize MBPP/HumanEval into master, SFT, and RL JSONL files."""

from __future__ import annotations

import argparse
import ast
import json
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


def load_humaneval_parquet(path: Path) -> list[dict[str, Any]]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError(
            "Reading HumanEval parquet requires pandas and pyarrow/fastparquet. "
            "Install them first, for example: pip install pandas pyarrow"
        ) from exc

    try:
        df = pd.read_parquet(path)
    except ImportError as exc:
        raise RuntimeError(
            "Reading HumanEval parquet requires pyarrow or fastparquet. "
            "Install one first, for example: pip install pyarrow"
        ) from exc

    return df.to_dict(orient="records")


def ensure_trailing_newline(text: str) -> str:
    text = text.replace("\r\n", "\n").strip("\n")
    return text + "\n"


def detect_entry_point_from_code(code: str) -> str | None:
    try:
        module = ast.parse(code)
    except SyntaxError:
        return None

    for node in module.body:
        if isinstance(node, ast.FunctionDef):
            return node.name
    return None


def render_mbpp_test_code(record: dict[str, Any]) -> str:
    parts: list[str] = []

    setup = (record.get("test_setup_code") or "").strip()
    if setup:
        parts.append(setup)

    imports = record.get("test_imports") or []
    for item in imports:
        item = str(item).strip()
        if item:
            parts.append(item)

    tests = record.get("test_list") or []
    parts.extend(str(test).strip() for test in tests if str(test).strip())

    return "\n".join(parts).strip()


def render_humaneval_test_code(record: dict[str, Any]) -> str:
    test_body = ensure_trailing_newline(record["test"])
    entry_point = record["entry_point"]
    return f"{test_body}\ncheck({entry_point})"


def normalize_mbpp_record(record: dict[str, Any], sanitized: bool) -> dict[str, Any]:
    prompt = record.get("prompt") or record.get("text") or ""
    solution = ensure_trailing_newline(record["code"])
    entry_point = detect_entry_point_from_code(solution)
    test_code = render_mbpp_test_code(record)

    return {
        "task_id": f"mbpp_{record['task_id']}",
        "source": "MBPP",
        "source_split": "train",
        "prompt": prompt.strip(),
        "entry_point": entry_point,
        "canonical_solution": solution,
        "test_cases": record.get("test_list") or [],
        "test_code": ensure_trailing_newline(test_code) if test_code else "",
        "language": "python",
        "metadata": {
            "sanitized": sanitized,
            "source_file": record.get("source_file"),
            "challenge_test_list": record.get("challenge_test_list") or [],
        },
    }


def normalize_humaneval_record(record: dict[str, Any]) -> dict[str, Any]:
    prompt = ensure_trailing_newline(record["prompt"])
    solution = record["canonical_solution"].replace("\r\n", "\n").rstrip("\n")
    full_solution = prompt + solution + "\n"

    return {
        "task_id": record["task_id"],
        "source": "HumanEval",
        "source_split": "test",
        "prompt": prompt,
        "entry_point": record["entry_point"],
        "canonical_solution": full_solution,
        "test_cases": [],
        "test_code": ensure_trailing_newline(render_humaneval_test_code(record)),
        "language": "python",
        "metadata": {},
    }


def build_sft_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": record["task_id"],
        "source": record["source"],
        "prompt": record["prompt"],
        "response": record["canonical_solution"],
        "entry_point": record["entry_point"],
        "language": record["language"],
    }


def build_rl_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "task_id": record["task_id"],
        "source": record["source"],
        "prompt": record["prompt"],
        "entry_point": record["entry_point"],
        "test_code": record["test_code"],
        "canonical_solution": record["canonical_solution"],
        "language": record["language"],
        "metadata": record["metadata"],
    }


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for record in records:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Normalize MBPP/HumanEval and export master/SFT/RL JSONL files."
    )
    parser.add_argument(
        "--mbpp",
        default="data/mbpp/mbpp_sanitized.jsonl",
        help="Path to MBPP JSONL file.",
    )
    parser.add_argument(
        "--humaneval",
        default="data/humaneval/openai_humaneval/test-00000-of-00001.parquet",
        help="Path to HumanEval parquet file.",
    )
    parser.add_argument(
        "--out-dir",
        default="data/processed",
        help="Directory to write normalized JSONL outputs.",
    )
    parser.add_argument(
        "--skip-humaneval",
        action="store_true",
        help="Only process MBPP.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    mbpp_path = (REPO_ROOT / args.mbpp).resolve()
    humaneval_path = (REPO_ROOT / args.humaneval).resolve()
    out_dir = (REPO_ROOT / args.out_dir).resolve()

    master_records: list[dict[str, Any]] = []

    mbpp_records = load_jsonl(mbpp_path)
    master_records.extend(
        normalize_mbpp_record(record, sanitized="sanitized" in mbpp_path.name)
        for record in mbpp_records
    )

    if not args.skip_humaneval:
        humaneval_records = load_humaneval_parquet(humaneval_path)
        master_records.extend(
            normalize_humaneval_record(record) for record in humaneval_records
        )

    sft_records = [build_sft_record(record) for record in master_records]
    rl_records = [build_rl_record(record) for record in master_records]

    write_jsonl(out_dir / "master.jsonl", master_records)
    write_jsonl(out_dir / "sft_all.jsonl", sft_records)
    write_jsonl(out_dir / "rl_all.jsonl", rl_records)

    summary = {
        "master_records": len(master_records),
        "mbpp_records": len([r for r in master_records if r["source"] == "MBPP"]),
        "humaneval_records": len(
            [r for r in master_records if r["source"] == "HumanEval"]
        ),
        "out_dir": str(out_dir),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
