# 任务进度记录表

## 当前阶段

- 当前聚焦：PPO 前的“生成-执行-打分”桥接
- 当前状态：数据准备完成，SFT 第一轮完成，Base vs SFT 第一版 A/B 对比完成
- 下一阶段：封装最小 `SandboxEnv` / rollout 接口，接入 PPO 训练循环

## 已完成事项

| 序号 | 任务 | 状态 | 结果 |
| --- | --- | --- | --- |
| 1 | 下载原始数据集 | 已完成 | 原始数据位于 `data/mbpp/` 与 `data/humaneval/` |
| 2 | 标准化数据格式 | 已完成 | 生成 `data/processed/master.jsonl`、`sft_all.jsonl`、`rl_all.jsonl` |
| 3 | 标准答案可执行性验证 | 已完成 | `591/591` 条样本本地验证通过 |
| 4 | 数据切分 | 已完成 | `MBPP -> train/valid`，`HumanEval -> test` |
| 5 | 导出最终训练文件 | 已完成 | 生成 `data/final/` 下的 SFT / RL 数据 |
| 6 | runtime 复核（MBPP valid） | 已完成 | `42/42` 通过 |
| 7 | runtime 复核（HumanEval test） | 已完成 | `164/164` 通过 |
| 8 | runtime 复核（MBPP train） | 已完成 | `385/385` 通过 |
| 9 | SFT 训练脚本骨架 | 已完成 | `scripts/train_sft.py` 与 `configs/sft_qwen25_coder_15b_lora.json` 已落地 |
| 10 | 1.5B 模型第一轮 SFT | 已完成 | 已完成 `Qwen2.5-Coder-1.5B + LoRA SFT` 训练并产出 adapter |
| 11 | SFT 训练结果验收 | 已完成 | `eval_loss = 0.7472`，并通过单题生成测试 |
| 12 | Base vs SFT A/B 评测脚本 | 已完成 | `scripts/evaluate_ab_models.py` 已落地 |
| 13 | Base vs SFT 第一版 A/B 评测 | 已完成 | `rl_valid` 上 `base=0/42`，`sft=3/42`，`Pass@1 +7.14%` |
| 14 | PPO 前桥接脚本 | 进行中 | `scripts/generate_execute_score.py` 已落地，待服务器联调 |

## 关键数据结论

### 数据规模

| 数据集 | 数量 | 说明 |
| --- | --- | --- |
| MBPP | 427 | 使用清洗后的可执行样本 |
| HumanEval | 164 | 标准化后用于测试 |
| 总计 | 591 | 全部进入统一 schema |

### 最终数据划分

| 文件 | 数量 | 用途 |
| --- | --- | --- |
| `data/final/sft_train.jsonl` | 385 | SFT 训练 |
| `data/final/sft_valid.jsonl` | 42 | SFT 验证 |
| `data/final/sft_test_humaneval.jsonl` | 164 | SFT 评测参考 |
| `data/final/rl_train.jsonl` | 385 | RL/PPO 训练输入 |
| `data/final/rl_valid.jsonl` | 42 | RL/PPO 验证 |
| `data/final/rl_test_humaneval.jsonl` | 164 | RL/PPO 测试 |

### 数据可用性

- `prompt` 空样本：`0`
- `entry_point` 缺失：`0`
- `canonical_solution` 空样本：`0`
- `test_code` 空样本：`0`
- 本地 Python 直跑验证：`591/591`
- runtime 复核失败样本：`0`

## 当前实验结论

### SFT 结果

- 模型：`Qwen2.5-Coder-1.5B`
- 方式：`LoRA SFT`
- 训练集：`385`
- 验证集：`42`
- 训练轮数：`5`
- 最终验证损失：`0.7472`

### Base vs SFT A/B 结果

- 评测集：`data/final/rl_valid.jsonl`
- Base `Pass@1`：`0/42 = 0.0`
- SFT `Pass@1`：`3/42 = 7.14%`
- 绝对提升：`+7.14%`
- 提升样本数：`3`
- 退化样本数：`0`

## 当前代码与脚本状态

### 已有关键脚本

- `scripts/prepare_datasets.py`
- `scripts/validate_dataset.py`
- `scripts/split_datasets.py`
- `scripts/validate_in_runtime.py`
- `scripts/train_sft.py`
- `scripts/evaluate_ab_models.py`
- `scripts/generate_execute_score.py`

### 当前最关键的新脚本

- `scripts/generate_execute_score.py`
  - 作用：读取 `rl_train/rl_valid` 样本
  - 使用模型生成代码
  - 本地执行 `test_code`
  - 输出 `reward / passed_tests / total_tests / pass_at_1`
  - 作为 PPO 前 rollout / reward 桥接原型

## 与计划对照后的判断

- 第一阶段目标：基本完成
  - 数据准备完成
  - SFT 热启动完成
- 第二阶段目标：已启动但未完成
  - PPO 前置桥接已开始
  - PPO training loop 仍未实现
  - Actor-Critic / GAE / KL 约束仍未实现
- 当前实际位置：
  - 已进入第二阶段前半段
  - 当前卡点是“生成-执行-打分”闭环到 PPO 更新的过渡

## 后续待办

- [ ] 在服务器上联调 `scripts/generate_execute_score.py`
- [ ] 固定 rollout 输出 schema，作为 PPO 输入
- [ ] 封装最小 `SandboxEnv` 原型
- [ ] 实现 PPO 训练骨架
- [ ] 接入 Actor-Critic / GAE / KL 约束
- [ ] 跑第一轮 SFT vs SFT+PPO baseline
