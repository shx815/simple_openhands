# 任务进度记录表

## 当前阶段

- 当前聚焦：训练数据整理与验收
- 当前状态：已完成原始数据整理、标准化、可执行性验证、训练/验证/测试切分
- 下一阶段：暂缓，等待进一步确认数据质量后再进入 SFT 或 RL 环节

## 已完成事项

| 序号 | 任务 | 状态 | 结果 |
| --- | --- | --- | --- |
| 1 | 下载原始数据集 | 已完成 | 已放入 `data/mbpp/` 与 `data/humaneval/` |
| 2 | 标准化数据格式 | 已完成 | 生成 `data/processed/master.jsonl`、`sft_all.jsonl`、`rl_all.jsonl` |
| 3 | 标准答案可执行性验证 | 已完成 | `591/591` 条样本通过 |
| 4 | 数据切分 | 已完成 | `MBPP -> train/valid`，`HumanEval -> test` |
| 5 | 导出最终训练文件 | 已完成 | 生成 `data/final/` 下 SFT/RL 两套数据 |
| 6 | 沙箱内 runtime 复核（MBPP valid） | 已完成 | `42/42` 条样本通过 |
| 7 | 沙箱内 runtime 复核（HumanEval test） | 已完成 | `164/164` 条样本通过 |
| 8 | 沙箱内 runtime 复核（MBPP train） | 已完成 | `385/385` 条样本通过 |

## 关键数据结论

### 原始与标准化规模

| 数据集 | 数量 | 说明 |
| --- | --- | --- |
| MBPP | 427 | 使用 `mbpp_sanitized.jsonl` |
| HumanEval | 164 | 从 parquet 读取并标准化 |
| 总计 | 591 | 已全部进入标准化主数据 |

### 验证结果

| 检查项 | 结果 |
| --- | --- |
| `prompt` 为空 | 0 |
| `entry_point` 缺失 | 0 |
| `canonical_solution` 为空 | 0 |
| `test_code` 为空 | 0 |
| 执行失败样本 | 0 |
| 超时样本 | 0 |
| runtime 复核失败样本 | 0 |

### 最终切分结果

| 文件 | 数量 | 用途 |
| --- | --- | --- |
| `data/final/sft_train.jsonl` | 385 | SFT 训练 |
| `data/final/sft_valid.jsonl` | 42 | SFT 验证 |
| `data/final/sft_test_humaneval.jsonl` | 164 | SFT 评测参考 |
| `data/final/rl_train.jsonl` | 385 | RL/PPO 训练环境输入 |
| `data/final/rl_valid.jsonl` | 42 | RL/PPO 验证 |
| `data/final/rl_test_humaneval.jsonl` | 164 | RL/PPO 测试集 |

## 当前数据格式约定

### Master 数据字段

- `task_id`
- `source`
- `source_split`
- `prompt`
- `entry_point`
- `canonical_solution`
- `test_cases`
- `test_code`
- `language`
- `metadata`

### SFT 数据字段

- `task_id`
- `source`
- `prompt`
- `response`
- `entry_point`
- `language`

### RL 数据字段

- `task_id`
- `source`
- `prompt`
- `entry_point`
- `test_code`
- `canonical_solution`
- `language`
- `metadata`

## 已确认的可用性结论

- 所有最终样本字段结构一致，适合批量读取。
- `MBPP` 与 `HumanEval` 已统一到同一主数据 schema。
- 所有样本均通过“标准答案 + 测试代码”的直接执行验证。
- `MBPP valid` 已在真实 runtime 中复核，`42/42` 通过。
- `HumanEval test` 已在真实 runtime 中复核，`164/164` 通过。
- `MBPP train` 已在真实 runtime 中复核，`385/385` 通过。
- 当前数据已经足够支持后续 `SFT` 热启动和 `RL` 环境接入。

## 风险与提醒

- 工作区内同时存在 `data/` 与 `DATA/` 显示混用现象。Windows 下通常不影响读写，但后续建议统一只使用 `data/` 这一种写法。
- 当前验证属于本地 Python 直接执行验证，还不等同于后续 Docker/FastAPI 沙箱中的最终环境验证。
- Docker/FastAPI runtime 级别复核已覆盖 `MBPP train`、`MBPP valid` 与 `HumanEval test`。
- `HumanEval` 更适合作为测试集，当前不建议混入训练集。

## 后续待办

- [ ] 再做一次基于运行时或沙箱环境的执行验证
- [ ] 确认 SFT 数据加载器输入格式
- [ ] 确认 RL 环境读取 `rl_train.jsonl` 的接口约定
- [ ] 进入下一阶段前，固定实验配置与评测口径
