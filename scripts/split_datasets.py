#!/usr/bin/env python3
"""Split validated datasets into train/valid/test exports for SFT and RL."""

from __future__ import annotations

import argparse
import json
import random
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
        "metadata": record.get("metadata", {}),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Split validated records into SFT/RL train-valid-test exports."
    )
    parser.add_argument(
        "--input",
        default="data/validated/passed.jsonl",
        help="Path to validated passed JSONL.",
    )
    parser.add_argument(
        "--out-dir",
        default="data/final",
        help="Directory to write split outputs.",
    )
    parser.add_argument(
        "--valid-ratio",
        type=float,
        default=0.1,
        help="Validation ratio for MBPP.",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for deterministic MBPP split.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = (REPO_ROOT / args.input).resolve()
    out_dir = (REPO_ROOT / args.out_dir).resolve()

    records = load_jsonl(input_path)
    mbpp_records = [record for record in records if record["source"] == "MBPP"]
    humaneval_records = [record for record in records if record["source"] == "HumanEval"]

    rng = random.Random(args.seed)
    mbpp_shuffled = list(mbpp_records)
    rng.shuffle(mbpp_shuffled)

    valid_size = int(len(mbpp_shuffled) * args.valid_ratio)
    if valid_size <= 0 and mbpp_shuffled:
        valid_size = 1

    mbpp_valid = mbpp_shuffled[:valid_size]
    mbpp_train = mbpp_shuffled[valid_size:]

    exports: dict[str, list[dict[str, Any]]] = {
        "master_train.jsonl": mbpp_train,
        "master_valid.jsonl": mbpp_valid,
        "master_test_humaneval.jsonl": humaneval_records,
        "sft_train.jsonl": [build_sft_record(record) for record in mbpp_train],
        "sft_valid.jsonl": [build_sft_record(record) for record in mbpp_valid],
        "sft_test_humaneval.jsonl": [
            build_sft_record(record) for record in humaneval_records
        ],
        "rl_train.jsonl": [build_rl_record(record) for record in mbpp_train],
        "rl_valid.jsonl": [build_rl_record(record) for record in mbpp_valid],
        "rl_test_humaneval.jsonl": [
            build_rl_record(record) for record in humaneval_records
        ],
    }

    for filename, export_records in exports.items():
        write_jsonl(out_dir / filename, export_records)

    summary = {
        "input_records": len(records),
        "mbpp_train": len(mbpp_train),
        "mbpp_valid": len(mbpp_valid),
        "humaneval_test": len(humaneval_records),
        "valid_ratio": args.valid_ratio,
        "seed": args.seed,
        "out_dir": str(out_dir),
    }
    (out_dir / "split_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
