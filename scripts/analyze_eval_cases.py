from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a compact markdown case analysis from Base/SFT/PPO scored outputs."
    )
    parser.add_argument("--base", required=True, help="Base scored_rollouts.jsonl")
    parser.add_argument("--sft", required=True, help="SFT scored_rollouts.jsonl")
    parser.add_argument("--ppo", required=True, help="PPO scored_rollouts.jsonl")
    parser.add_argument("--out", required=True, help="Output markdown file")
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Maximum examples per category.",
    )
    return parser.parse_args()


def load_jsonl(path: Path) -> dict[str, dict[str, Any]]:
    records: dict[str, dict[str, Any]] = {}
    with path.open("r", encoding="utf-8") as fh:
        for line in fh:
            if not line.strip():
                continue
            record = json.loads(line)
            task_id = record.get("task_id")
            if not task_id:
                continue
            records[task_id] = record
    return records


def passed(record: dict[str, Any]) -> bool:
    return bool(record.get("passed"))


def short_text(value: Any, max_chars: int = 700) -> str:
    text = "" if value is None else str(value)
    text = text.replace("\r\n", "\n").strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rstrip() + "\n..."


def status(record: dict[str, Any]) -> str:
    return "pass" if passed(record) else "fail"


def reward(record: dict[str, Any]) -> str:
    value = record.get("reward")
    if isinstance(value, (int, float)):
        return f"{value:.4f}"
    return "NA"


def case_block(task_id: str, base: dict[str, Any], sft: dict[str, Any], ppo: dict[str, Any]) -> str:
    prompt = short_text(ppo.get("prompt") or sft.get("prompt") or base.get("prompt"), 500)
    entry_point = ppo.get("entry_point") or sft.get("entry_point") or base.get("entry_point") or "NA"
    rows = [
        f"### {task_id}",
        "",
        f"- entry_point: `{entry_point}`",
        f"- Base: {status(base)}, reward={reward(base)}, error={base.get('error_type') or 'NA'}",
        f"- SFT: {status(sft)}, reward={reward(sft)}, error={sft.get('error_type') or 'NA'}",
        f"- PPO: {status(ppo)}, reward={reward(ppo)}, error={ppo.get('error_type') or 'NA'}",
        "",
        "Prompt:",
        "",
        "```text",
        prompt,
        "```",
        "",
        "Base solution:",
        "",
        "```python",
        short_text(base.get("generated_solution")),
        "```",
        "",
        "SFT solution:",
        "",
        "```python",
        short_text(sft.get("generated_solution")),
        "```",
        "",
        "PPO solution:",
        "",
        "```python",
        short_text(ppo.get("generated_solution")),
        "```",
        "",
        "分析：待人工补充。建议说明 PPO 是否修复了入口函数、边界条件、循环逻辑、返回类型或异常输出。",
        "",
    ]
    return "\n".join(rows)


def collect_cases(
    base_records: dict[str, dict[str, Any]],
    sft_records: dict[str, dict[str, Any]],
    ppo_records: dict[str, dict[str, Any]],
    limit: int,
) -> dict[str, list[tuple[str, dict[str, Any], dict[str, Any], dict[str, Any]]]]:
    categories = {
        "PPO 修复 SFT": [],
        "PPO 相比 SFT 退化": [],
        "Base/SFT/PPO 全部通过": [],
        "Base/SFT/PPO 全部失败": [],
    }
    task_ids = sorted(set(base_records) & set(sft_records) & set(ppo_records))
    for task_id in task_ids:
        base = base_records[task_id]
        sft = sft_records[task_id]
        ppo = ppo_records[task_id]
        item = (task_id, base, sft, ppo)
        if not passed(sft) and passed(ppo):
            categories["PPO 修复 SFT"].append(item)
        if passed(sft) and not passed(ppo):
            categories["PPO 相比 SFT 退化"].append(item)
        if passed(base) and passed(sft) and passed(ppo):
            categories["Base/SFT/PPO 全部通过"].append(item)
        if not passed(base) and not passed(sft) and not passed(ppo):
            categories["Base/SFT/PPO 全部失败"].append(item)
    return {name: items[:limit] for name, items in categories.items()}


def main() -> int:
    args = parse_args()
    base_records = load_jsonl(Path(args.base))
    sft_records = load_jsonl(Path(args.sft))
    ppo_records = load_jsonl(Path(args.ppo))
    categories = collect_cases(base_records, sft_records, ppo_records, args.limit)

    lines = [
        "# Base/SFT/PPO 案例分析",
        "",
        "本文档由 scripts/analyze_eval_cases.py 自动生成，具体原因分析需要人工补充。",
        "",
        "## 汇总",
        "",
        f"- Base 样本数：{len(base_records)}",
        f"- SFT 样本数：{len(sft_records)}",
        f"- PPO 样本数：{len(ppo_records)}",
        "",
    ]
    for category, items in categories.items():
        lines.extend([f"## {category}", ""])
        if not items:
            lines.extend(["暂无样例。", ""])
            continue
        for task_id, base, sft, ppo in items:
            lines.append(case_block(task_id, base, sft, ppo))

    Path(args.out).write_text("\n".join(lines), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
