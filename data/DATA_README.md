# Data Directory Guide

## 该用哪个目录

如果你现在要真正开始训练，直接使用 `data/final/` 里的文件。

### SFT

- `data/final/sft_train.jsonl`
- `data/final/sft_valid.jsonl`

### RL / PPO

- `data/final/rl_train.jsonl`
- `data/final/rl_valid.jsonl`

### 测试 / 评测

- `data/final/rl_test_humaneval.jsonl`

## 目录说明

### `data/mbpp/`

- MBPP 原始数据
- 不直接用于训练

### `data/humaneval/`

- HumanEval 原始数据
- 不直接用于训练

### `data/processed/`

- 标准化后的中间数据
- 包含统一 schema 的主数据：
  - `master.jsonl`
  - `sft_all.jsonl`
  - `rl_all.jsonl`

### `data/validated/`

- 本地 Python 直接执行的验证结果
- 用来确认标准答案和测试代码在本地环境中可运行

### `data/final/`

- 最终训练数据
- 这是当前项目最重要的数据目录

包含：

- `master_train.jsonl`
- `master_valid.jsonl`
- `master_test_humaneval.jsonl`
- `sft_train.jsonl`
- `sft_valid.jsonl`
- `sft_test_humaneval.jsonl`
- `rl_train.jsonl`
- `rl_valid.jsonl`
- `rl_test_humaneval.jsonl`
- `split_summary.json`

### `data/runtime_validated/`

- `MBPP valid` 在 runtime / sandbox 中的复核结果

### `data/runtime_validated_humaneval/`

- `HumanEval test` 在 runtime / sandbox 中的复核结果

### `data/runtime_validated_train/`

- `MBPP train` 在 runtime / sandbox 中的复核结果

## 当前最终数据规模

- `MBPP train`: 385
- `MBPP valid`: 42
- `HumanEval test`: 164

## 当前数据结论

- 原始数据已经完成标准化
- 字段格式已经统一
- 本地执行验证已完成
- runtime / sandbox 复核已完成
- 当前可以直接使用 `data/final/` 中的数据进入后续训练阶段

## 推荐使用顺序

1. 先做 SFT：
   - `data/final/sft_train.jsonl`
   - `data/final/sft_valid.jsonl`
2. 再做 RL：
   - `data/final/rl_train.jsonl`
   - `data/final/rl_valid.jsonl`
3. 最后评测：
   - `data/final/rl_test_humaneval.jsonl`

## 注意事项

- `data/mbpp/` 和 `data/humaneval/` 是原始数据，不要直接拿去训练。
- `data/processed/` 和 `data/validated/` 是中间产物，主要用于追踪和复核。
- 真正训练时优先看 `data/final/`。
