# 论文实验材料整理

本文档用于支撑论文实验设置、数据集说明、训练配置与可复现性描述。

## 1. 数据集统计

最终使用的数据来自 MBPP 和 HumanEval。MBPP 用于 SFT 训练、SFT 验证、PPO rollout 和 PPO 验证；HumanEval 用于最终测试集评估。

| 文件 | 样本数 | 来源 | 用途 | 主要字段 |
|---|---:|---|---|---|
| data/final/master_train.jsonl | 385 | MBPP | 统一主数据 train | task_id, prompt, canonical_solution, entry_point, test_code, test_cases |
| data/final/master_valid.jsonl | 42 | MBPP | 统一主数据 valid | task_id, prompt, canonical_solution, entry_point, test_code, test_cases |
| data/final/master_test_humaneval.jsonl | 164 | HumanEval | 统一主数据 test | task_id, prompt, canonical_solution, entry_point, test_code |
| data/final/sft_train.jsonl | 385 | MBPP | SFT 训练 | task_id, prompt, response, entry_point |
| data/final/sft_valid.jsonl | 42 | MBPP | SFT 验证 | task_id, prompt, response, entry_point |
| data/final/sft_test_humaneval.jsonl | 164 | HumanEval | SFT 测试参考 | task_id, prompt, response, entry_point |
| data/final/rl_train.jsonl | 385 | MBPP | PPO rollout 训练池 | task_id, prompt, canonical_solution, entry_point, test_code |
| data/final/rl_valid.jsonl | 42 | MBPP | PPO 验证集 | task_id, prompt, canonical_solution, entry_point, test_code |
| data/final/rl_test_humaneval.jsonl | 164 | HumanEval | 最终测试集 | task_id, prompt, canonical_solution, entry_point, test_code |

数据划分：

- 总样本数：591
- MBPP train：385
- MBPP valid：42
- HumanEval test：164
- valid_ratio：0.1
- random seed：42

Prompt 长度统计：

| 数据集 | prompt 最短字符数 | prompt 平均字符数 | prompt 最长字符数 |
|---|---:|---:|---:|
| MBPP train | 39 | 92.9 | 410 |
| MBPP valid | 44 | 90.0 | 210 |
| HumanEval test | 113 | 449.5 | 1359 |

数据可用性复核：

| 复核集 | 输入样本数 | 通过样本数 | 失败样本数 | pass_rate |
|---|---:|---:|---:|---:|
| 全量格式复核 | 591 | 591 | 0 | 1.0 |
| MBPP valid runtime 复核 | 42 | 42 | 0 | 1.0 |
| MBPP train runtime 复核 | 385 | 385 | 0 | 1.0 |
| HumanEval runtime 复核 | 164 | 164 | 0 | 1.0 |

结论：最终数据字段统一，训练、验证和测试文件均可被当前脚本直接读取；标准答案在 runtime 复核中均通过，说明测试代码和入口函数字段可用。

## 2. 模型与训练配置

### 2.1 基座模型

| 项目 | 设置 |
|---|---|
| 模型 | Qwen2.5-Coder-1.5B |
| 本地服务器路径 | /root/autodl-tmp/models/Qwen2.5-Coder-1.5B |
| 模型类型 | 代码专用因果语言模型 |
| 作用 | Base 评测、SFT 初始化、PPO policy 初始化 |

说明：Qwen2.5-Coder-1.5B 本身已经经过大规模代码数据训练，因此论文中应将其表述为强代码基座模型，而不是未训练的随机初始化模型。

### 2.2 SFT 配置

| 参数 | 值 |
|---|---|
| train_file | data/final/sft_train.jsonl |
| valid_file | data/final/sft_valid.jsonl |
| output_dir | outputs/sft-qwen25-coder-15b-lora |
| max_length | 1024 |
| num_train_epochs | 5 |
| per_device_train_batch_size | 2 |
| per_device_eval_batch_size | 2 |
| gradient_accumulation_steps | 8 |
| learning_rate | 1e-4 |
| weight_decay | 0.01 |
| warmup_ratio | 0.05 |
| bf16 | true |
| gradient_checkpointing | true |
| LoRA r | 16 |
| LoRA alpha | 32 |
| LoRA dropout | 0.1 |
| LoRA target modules | q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj |
| seed | 42 |

SFT 最终验证结果：

- eval_loss：0.7472
- 训练耗时：约 5 分钟
- 验证集 Pass@1：0.5714
- HumanEval 测试集 Pass@1：0.5244

### 2.3 PPO 配置

当前 PPO 实现属于单步 episode 的简化 PPO 闭环，包含：

- rollout 收集
- 本地代码执行
- reward 计算
- advantage 预处理
- clipped policy loss
- value loss
- KL penalty
- LoRA adapter 更新

主要 PPO 参数：

| 参数 | 主要取值 |
|---|---|
| epochs | 1 |
| batch_size | 4 |
| clip_eps | 0.2 |
| value_coef | 0.5 |
| gamma | 1.0 |
| gae_lambda | 1.0 |
| learning_rate | 1e-5 或 5e-6 |
| kl_coef | 0.02 或 0.01 |
| rollout 数量 | 42 或 100 |

当前 best PPO：

| 项目 | 值 |
|---|---|
| 实验名 | exp1_reward_v2 |
| adapter 目录 | outputs/ppo_policy_update_valid_exp1_reward_v2 |
| rollout 来源 | rl_valid 42 条 |
| learning_rate | 1e-5 |
| kl_coef | 0.02 |
| reward | reward_v2 |
| valid Pass@1 | 0.6667 |
| HumanEval Pass@1 | 0.5122 |

## 3. Reward 设计

### 3.1 原始 reward

原始 reward 主要依据测试通过比例，信号较稀疏。实验中 PPO exp1 能超过 SFT baseline，但提升有限。

### 3.2 reward_v2

reward_v2 是当前最终采用的主奖励：

- 代码可执行：0.1
- 测试通过比例：0.8 * pass_ratio
- 全部测试通过：0.1
- reward 上限：1.0

reward_v2 的作用是将代码生成质量拆成可执行、部分正确和完全正确三个层次，使 PPO 获得更密集的执行反馈。

### 3.3 reward_v3 与 reward_v3b

reward_v3 在 reward_v2 基础上加入 AST 结构相似度和函数签名匹配奖励。reward_v3b 降低结构奖励权重，并提高测试通过比例权重。

最终结果表明：

- reward_v3：valid Pass@1 = 0.5952，average_reward = 0.7311
- reward_v3b：valid Pass@1 = 0.5952，average_reward = 0.6749
- reward_v2：valid Pass@1 = 0.6667，average_reward = 0.7190

结论：结构奖励能影响 reward 数值，但没有提升 Pass@1。当前小数据和单步 PPO 设置下，执行测试反馈比结构相似度代理指标更可靠。

## 4. 实验环境

主要服务器环境：

| 项目 | 配置 |
|---|---|
| 平台 | AutoDL |
| GPU | NVIDIA GeForce RTX 4090 D 24GB |
| CPU | 16 核 |
| 内存 | 60GB |
| Python | 3.12 |
| PyTorch | 2.11.0+cu130 |
| CUDA 驱动能力 | CUDA 13.0 |
| 主要工作目录 | /root/autodl-tmp/work/simple_openhands |
| 模型缓存目录 | /root/autodl-tmp/models |

本地开发环境：

| 项目 | 配置 |
|---|---|
| 系统 | Windows |
| 仓库路径 | C:\Users\sunhaixiang\Desktop\simple_openhands |
| 分支 | dev |

## 5. 论文可写结论

1. 数据规模虽然不大，但经过格式统一和 runtime 复核后，数据质量可控。

2. SFT、PPO、reward 消融和测试集泛化评估已经构成完整实验链路。

3. PPO 的最佳结果不是单次偶然实验，而是通过 learning_rate、kl_coef、rollout 数量和 reward 设计多组对照得到。

4. reward_v3/v3b 的负向结果可以写入消融实验，说明奖励函数不是越复杂越好，当前任务中执行反馈仍是最有效信号。
