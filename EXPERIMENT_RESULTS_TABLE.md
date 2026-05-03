# 实验结果标准对照表

## 1. 验证集结果对照

数据集：rl_valid  
样本数：42

| 实验组 | 主要设置 | Pass@1 | full_pass_records | average_reward | 结论 |
|---|---|---:|---:|---:|---|
| Base | Qwen2.5-Coder-1.5B，未做 SFT/PPO | 0.6667 | 28 | 0.7381 | 强后处理口径下，基座模型在 valid 上已经较强 |
| SFT baseline | SFT adapter，未做 PPO | 0.5714 | 24 | 0.6524 | 小样本 SFT 后 valid 表现低于 Base |
| PPO exp1 | 原始 reward，rollout=42，lr=1e-5，kl=0.02 | 0.6190 | 26 | 0.6270 | 首次优于 SFT baseline |
| PPO exp2 | 原始 reward，rollout=42，lr=1e-5，kl=0.01 | 0.5476 | 23 | 0.5794 | 单独降低 kl_coef 无效 |
| PPO exp3 | 原始 reward，rollout=42，lr=5e-6，kl=0.02 | 0.5952 | 25 | 0.6190 | 更稳，但不如 exp1 |
| PPO exp4 | 原始 reward，rollout=100，lr=1e-5，kl=0.02 | 0.5714 | 24 | 0.6111 | 扩大 rollout 未提升 |
| PPO exp5 | 原始 reward，rollout=100，lr=5e-6，kl=0.02 | 0.5714 | 24 | 0.6032 | 大 rollout + 小 lr 仍无提升 |
| SFT baseline reward_v2 | reward shaping 后重新评测 | 0.5714 | 24 | 0.6524 | 新 reward 口径基线 |
| PPO exp1_reward_v2 | reward_v2，rollout=42，lr=1e-5，kl=0.02 | 0.6667 | 28 | 0.7190 | 当前最佳结果 |
| PPO exp2_reward_v2_lr5e6 | reward_v2，rollout=42，lr=5e-6，kl=0.02 | 0.6190 | 26 | 0.6762 | 有提升，但不如最佳结果 |
| PPO exp1_reward_v3 | reward_v3，加入 AST 相似度与函数签名奖励，rollout=42，lr=1e-5，kl=0.02 | 0.5952 | 25 | 0.7311 | 平均 reward 最高，但 Pass@1 低于 reward_v2 |
| PPO exp1_reward_v3b | reward_v3b，降低结构奖励权重，rollout=42，lr=1e-5，kl=0.02 | 0.5952 | 25 | 0.6749 | 降低结构权重后仍未改善 Pass@1 |

## 2. 测试集结果对照

数据集：rl_test_humaneval  
样本数：164

| 实验组 | 主要设置 | Pass@1 | full_pass_records | average_reward | generation_execution_failures | 结论 |
|---|---|---:|---:|---:|---:|---|
| Base | Qwen2.5-Coder-1.5B，未做 SFT/PPO | 0.5000 | 82 | 0.5457 | 7 | 基座模型具备较强 HumanEval 能力 |
| SFT baseline | SFT adapter | 0.5244 | 86 | 0.5707 | 2 | 测试集上略优于 Base |
| PPO best | exp1_reward_v2 最佳 adapter | 0.5122 | 84 | 0.5610 | 0 | 低于 SFT baseline，但 execution failure 最少 |

## 3. 关键观察

1. 在验证集上，PPO 在合适设置下能够修复 SFT 后模型的性能下降。当前最佳结果 exp1_reward_v2 的 Pass@1 从 SFT 的 0.5714 提升到 0.6667，追平 Base。

2. 在强后处理评测口径下，Base 模型在 valid 上已经具备较强能力，说明 Qwen2.5-Coder-1.5B 的代码预训练能力很强，小样本 SFT 不一定带来验证集增益。

3. 单独降低 kl_coef 或单独降低 learning_rate 都未能超过 exp1，说明当前实现中 PPO 对超参数较敏感。

4. 将 rollout 从 42 扩大到 100 后，性能并未继续提升，说明更大的 rollout 规模需要与 update 强度协同设计。

5. reward shaping 是目前最有效的改进项。相比原始 reward，新的 reward 设计显著提升了 PPO 的训练效果。

6. reward_v3 和 reward_v3b 尝试引入 AST 相似度与函数签名等结构奖励，但两组实验的 Pass@1 均为 0.5952，低于 reward_v2 的 0.6667。说明在当前小数据和单步 PPO 设置下，结构相似性奖励与最终测试通过率并不完全一致。

7. 在 HumanEval 测试集上，SFT 相比 Base 有小幅提升，但当前最佳 PPO 模型略低于 SFT baseline，说明目前 PPO 的增益主要体现在验证集，跨数据集泛化能力仍有欠缺。

## 4. 当前可写入论文的阶段性结论

1. 本文已实现从 SFT 到 PPO 的完整训练闭环，包括代码生成、执行测试、奖励计算、优势估计和策略更新等关键模块。

2. 在验证集上，PPO 结合 reward shaping v2 后能够明显优于 SFT baseline，并追平 Base 的 Pass@1，证明基于执行反馈的优化策略能够改善小样本 SFT 后的策略表现。

3. 结构奖励 v3/v3b 未能超过 reward_v2，说明当前阶段最有效的奖励仍是以执行正确性为核心的密集 reward，而不是更复杂的结构相似度代理指标。

4. 当前方法在测试集上的泛化能力仍有限，说明后续仍需在 reward 设计、训练稳定性和跨任务泛化方面继续优化。
