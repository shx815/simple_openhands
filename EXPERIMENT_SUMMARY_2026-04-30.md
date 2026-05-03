# 2026-04-30 实验结果汇总

## 1. 实验背景

本轮实验在新服务器环境下重新恢复并继续推进 PPO 调参实验。由于旧服务器实例已经释放，本次先完成了以下恢复工作：

- 重新创建服务器实例并配置工作目录
- 重新 clone dev 分支代码
- 重新创建 Python 虚拟环境并安装依赖
- 重新下载基座模型 Qwen2.5-Coder-1.5B
- 从本地备份恢复 SFT 训练产物 outputs/sft-qwen25-coder-15b-lora

恢复完成后，重新确认了 SFT baseline 的有效性，然后围绕 PPO update 的 rollout 规模、learning rate、kl_coef，以及 reward shaping 进行了实验。

## 2. SFT baseline 恢复结果

在 rl_valid 全量 42 条样本上重新评测 SFT adapter，结果如下：

- total_records: 42
- full_pass_records: 24
- pass_at_1: 0.5714
- average_reward: 0.619
- generation_execution_failures: 0

该结果与此前记录一致，说明：

- SFT adapter 恢复正确
- 当前服务器环境正常
- 后续 PPO 实验可以以该 baseline 为参照继续进行

## 3. PPO 第一轮全量实验结果

### 3.1 rollout 基线

先使用 rl_valid 全量 42 条样本重新收集 rollout，结果如下：

- total_rollouts: 42
- pass_at_1: 0.5714
- average_reward: 0.619

该 rollout 结果与 SFT baseline 一致，说明 rollout 收集和 reward 计算链路稳定。

### 3.2 PPO exp1

在以下参数设置下进行 PPO update：

- epochs: 1
- batch_size: 4
- learning_rate: 1e-5
- clip_eps: 0.2
- value_coef: 0.5
- kl_coef: 0.02
- gamma: 1.0
- gae_lambda: 1.0
- rollout 数量: 42

PPO update 摘要：

- mean_total_loss: 6.210515
- mean_policy_loss: -1.499065
- mean_value_loss: 1.606661
- mean_kl_loss: 345.545455
- mean_ratio: 1.215104

更新后在 rl_valid 全量上的评测结果：

- full_pass_records: 26
- pass_at_1: 0.619
- average_reward: 0.627

与 SFT baseline 相比：

- Pass@1 从 0.5714 提升到 0.619
- average_reward 从 0.619 提升到 0.627

结论：

- PPO 在当前实现下已经能够带来真实的正向收益
- 这是当前实验中首次得到明确优于 SFT baseline 的 PPO 结果

## 4. 第一轮调参结果

### 4.1 exp2：降低 kl_coef

参数调整：

- learning_rate: 1e-5
- kl_coef: 0.01

结果：

- pass_at_1: 0.5476
- average_reward: 0.5794
- mean_ratio: 1.957645
- mean_kl_loss: 355.818182

结论：

- 单独降低 kl_coef 并没有改善结果
- 策略偏移反而更大
- 该方向不适合作为当前阶段的优先优化路径

### 4.2 exp3：降低 learning_rate

参数调整：

- learning_rate: 5e-6
- kl_coef: 0.02

结果：

- pass_at_1: 0.5952
- average_reward: 0.619
- mean_ratio: 1.005761
- mean_kl_loss: 341.363636

结论：

- 降低 learning_rate 后，更新更稳
- 但整体结果仍未超过 exp1
- 说明更保守的更新未带来更优性能

## 5. 第二轮实验：扩大 rollout 规模

为了验证更大 rollout 是否能进一步提升效果，使用 rl_train 抽取 100 条样本重新收集 rollout。

rollout 结果：

- total_rollouts: 100
- pass_at_1: 0.59
- average_reward: 0.6267

### 5.1 exp4：100 rollout + learning_rate 1e-5

结果：

- pass_at_1: 0.5714
- average_reward: 0.6111
- mean_ratio: 1.349951
- mean_kl_loss: 310.84

结论：

- 扩大 rollout 规模到 100 后，没有超过 exp1
- 说明在当前实现下，更多 rollout 并未自动转化为更好性能

### 5.2 exp5：100 rollout + learning_rate 5e-6

结果：

- pass_at_1: 0.5714
- average_reward: 0.6032
- mean_ratio: 1.632411
- mean_kl_loss: 315.8

结论：

- 在 100 rollout 条件下进一步降低 learning_rate，也没有得到更优结果
- 当前实现下，大 rollout 并不比 42 条 rollout 更适合

## 6. reward shaping 实验

在前述实验基础上，判断原始 reward 信号较稀疏，因此对 reward 规则进行了重新设计。

新的 reward 规则：

- 代码可执行：奖励 0.1
- 测试通过比例：奖励 0.8 * pass_ratio
- 全部测试通过：额外奖励 0.1
- reward 上限保持为 1.0

该 reward shaping 已统一接入：

- generate_execute_score.py
- ppo_rollout_loop.py
- LocalCodeSandboxEnv

### 6.1 reward shaping 下的新 baseline

使用 SFT adapter 重新评测 rl_valid 全量 42 条样本：

- pass_at_1: 0.5714
- average_reward: 0.6524

说明：

- Pass@1 不变
- average_reward 提升，表明新的 reward 更密、更适合作为 PPO 信号

### 6.2 exp1_reward_v2

参数保持：

- epochs: 1
- batch_size: 4
- learning_rate: 1e-5
- kl_coef: 0.02

PPO update 摘要：

- mean_total_loss: 7.143796
- mean_policy_loss: 0.302645
- mean_value_loss: 0.767528
- mean_kl_loss: 322.818182
- mean_ratio: 0.559183

更新后评测结果：

- full_pass_records: 28
- pass_at_1: 0.6667
- average_reward: 0.719

与 reward_v2 baseline 相比：

- Pass@1 从 0.5714 提升到 0.6667
- average_reward 从 0.6524 提升到 0.719

与此前最好结果 exp1 相比：

- Pass@1 从 0.619 提升到 0.6667
- average_reward 从 0.627 提升到 0.719

结论：

- reward shaping 是本轮实验最关键的改进
- 在 reward_v2 条件下，PPO 获得了截至目前最好的整体结果

### 6.3 exp2_reward_v2_lr5e6

在 reward_v2 基础上进一步降低 learning_rate 到 5e-6，结果如下：

- pass_at_1: 0.619
- average_reward: 0.6762
- mean_ratio: 0.835878
- mean_kl_loss: 335.454545

结论：

- 结果优于旧 baseline，但不如 exp1_reward_v2
- 进一步降低 learning_rate 没有继续提升性能

## 7. 当前最佳实验结果

截至目前，最佳结果为：

- 实验名：exp1_reward_v2
- adapter 目录：outputs/ppo_policy_update_valid_exp1_reward_v2

指标如下：

- total_records: 42
- full_pass_records: 28
- pass_at_1: 0.6667
- average_reward: 0.719
- generation_execution_failures: 0

相对 SFT baseline 的提升：

- Pass@1：0.5714 -> 0.6667
- full_pass_records：24 -> 28
- average_reward：0.6524 -> 0.719（按新 reward 口径）

## 8. 阶段性实验结论

本轮实验已经可以得出以下阶段性结论：

1. PPO 训练闭环已经跑通  
包括 rollout 收集、reward 计算、advantage 预处理、policy update、value loss、KL penalty 和更新后评测等关键环节均已实现并验证。

2. PPO 并非天然优于 SFT，超参数和 reward 设计对结果影响很大  
在原始 reward 条件下，PPO 只能带来小幅提升；在不合理的参数设定下还会出现退化。

3. rollout 规模不是越大越好  
在当前实现下，42 条 rollout 的效果优于 100 条 rollout。说明 rollout 规模需要与 update 强度、KL 约束和 reward 设计协同匹配。

4. reward shaping 是当前最有效的提升手段  
相比直接调 learning_rate 或 kl_coef，reward 信号的改进带来了更明显、更稳定的性能提升。

5. 当前最优结果已经能够支撑中期阶段的实验结论  
基于 exp1_reward_v2，已经可以明确说明：在 SFT 基础上加入 PPO，并采用更合理的 reward shaping，模型在代码任务上的 Pass@1 指标获得了明显提升。

## 9. 后续建议

下一阶段建议优先做以下工作：

1. 固化当前最佳结果并完成备份
2. 将最佳结果补充到实验总结、中期报告和计划文档中
3. 在 rl_test_humaneval 上对当前最佳 PPO adapter 做测试集评估
4. 如仍需进一步优化，可考虑：
   - 更系统的 reward shaping 设计
   - 更稳定的多步 trajectory PPO
   - 更完整的 critic/value 训练
   - 在测试集上验证泛化能力

## 10. 最终补充：统一口径下的 PPO 调参路径

后续实验中对评测脚本进行了统一修正，主要包括：

- 对模型输出进行代码块和解释性文本清洗
- 对 HumanEval 的 check 函数调用方式进行修正
- 对 MBPP 和 HumanEval 使用统一的 generate-execute-score 评测口径
- 将 reward_v2、reward_v3 和 reward_v3b 都接入同一套 rollout 与评测流程

因此，论文最终实验部分应以统一口径下的结果为准。PPO 调参过程可以作为完整消融实验写入论文，而不只保留最终 best PPO。

### 10.1 验证集最终基线

数据集：rl_valid  
样本数：42

| 模型 | 设置 | Pass@1 | full_pass_records | average_reward | 说明 |
|---|---|---:|---:|---:|---|
| Base | Qwen2.5-Coder-1.5B，未做 SFT/PPO | 0.6667 | 28 | 0.7381 | 统一清洗口径下，基座模型本身已经较强 |
| SFT baseline | SFT adapter，未做 PPO | 0.5714 | 24 | 0.6524 | 小样本 SFT 后 valid 表现低于 Base |

这一结果说明，当前基座模型不是从零开始的普通模型，而是已经经过大规模代码数据训练的强代码模型。因此，论文中需要强调：本文的 PPO 目标不是从零训练代码能力，而是在强代码基座和小样本 SFT 基础上，验证执行反馈能否进一步修复和优化策略。

### 10.2 PPO 调参完整结果表

| 实验组 | rollout 来源与数量 | reward 设置 | learning_rate | kl_coef | Pass@1 | full_pass_records | average_reward | 结论 |
|---|---|---|---:|---:|---:|---:|---:|---|
| PPO exp1 | rl_valid 42 | 原始 reward | 1e-5 | 0.02 | 0.6190 | 26 | 0.6270 | 首次超过 SFT baseline |
| PPO exp2 | rl_valid 42 | 原始 reward | 1e-5 | 0.01 | 0.5476 | 23 | 0.5794 | 降低 kl_coef 后退化 |
| PPO exp3 | rl_valid 42 | 原始 reward | 5e-6 | 0.02 | 0.5952 | 25 | 0.6190 | 更稳，但低于 exp1 |
| PPO exp4 | rl_train 100 | 原始 reward | 1e-5 | 0.02 | 0.5714 | 24 | 0.6111 | 扩大 rollout 未提升 |
| PPO exp5 | rl_train 100 | 原始 reward | 5e-6 | 0.02 | 0.5714 | 24 | 0.6032 | 大 rollout + 小 lr 仍无提升 |
| PPO exp1_reward_v2 | rl_valid 42 | reward_v2，执行奖励 + 测试通过比例 + 全通过奖励 | 1e-5 | 0.02 | 0.6667 | 28 | 0.7190 | 当前 valid 最佳，追平 Base |
| PPO exp2_reward_v2_lr5e6 | rl_valid 42 | reward_v2 | 5e-6 | 0.02 | 0.6190 | 26 | 0.6762 | 优于 SFT，但低于 exp1_reward_v2 |
| PPO exp1_reward_v3 | rl_valid 42 | reward_v3，加入 AST 相似度与函数签名奖励 | 1e-5 | 0.02 | 0.5952 | 25 | 0.7311 | reward 数值高，但 Pass@1 不高 |
| PPO exp1_reward_v3b | rl_valid 42 | reward_v3b，降低结构奖励权重 | 1e-5 | 0.02 | 0.5952 | 25 | 0.6749 | 降低结构奖励后仍未超过 reward_v2 |

从完整调参路径可以看出：

1. PPO 的效果对 reward 设计和更新强度都比较敏感。  
原始 reward 下，exp1 能超过 SFT baseline，但 exp2、exp3、exp4、exp5 都没有继续提升，说明简单调整 kl_coef、learning_rate 或 rollout 数量并不足以稳定提高效果。

2. rollout 数量不是越大越好。  
使用 rl_train 100 条 rollout 后，exp4 和 exp5 都回落到 0.5714，说明当前单步 PPO 实现还不能简单依靠更多 rollout 获得收益，rollout 规模需要和 reward 密度、KL 约束、学习率共同匹配。

3. reward_v2 是目前最有效的改进。  
reward_v2 将代码可执行、测试通过比例和全部通过三个层次组合起来，使 PPO 在 valid 上从 SFT 的 0.5714 提升到 0.6667，追平 Base。

4. reward_v3 和 reward_v3b 提供了有价值的负向消融。  
结构奖励借鉴了代码生成强化学习论文中的思路，但在当前小数据集和单步 PPO 设置下没有提高 Pass@1。reward_v3 的 average_reward 达到 0.7311，却只得到 0.5952 的 Pass@1，说明结构相似度奖励可能提高代理分数，但不一定提高最终功能正确性。

### 10.3 测试集最终结果

数据集：rl_test_humaneval  
样本数：164

| 模型 | 设置 | Pass@1 | full_pass_records | average_reward | generation_execution_failures | 说明 |
|---|---|---:|---:|---:|---:|---|
| Base | Qwen2.5-Coder-1.5B，未做 SFT/PPO | 0.5000 | 82 | 0.5457 | 7 | 基座模型具备较强 HumanEval 能力 |
| SFT baseline | SFT adapter | 0.5244 | 86 | 0.5707 | 2 | 相比 Base 有小幅提升 |
| PPO best | exp1_reward_v2 | 0.5122 | 84 | 0.5610 | 0 | 低于 SFT，但执行失败最少 |

测试集结果表明，当前 PPO 的主要收益仍集中在 valid 分布上，尚未稳定迁移到 HumanEval 测试集。论文中应据此给出更稳健的表述：PPO + reward_v2 能够在验证集上修复 SFT 后的下降并追平 Base，但跨数据集泛化仍有限。

### 10.4 论文中建议采用的叙述方式

实验章节可以按如下逻辑展开：

1. 先说明 Base、SFT 和 PPO 的最终对比。  
Base 很强，SFT 在 HumanEval 上略有提升，但在 valid 上低于 Base；PPO best 在 valid 上显著优于 SFT 并追平 Base。

2. 再说明 PPO 调参过程。  
通过 exp1 到 exp5 证明 PPO 不是天然稳定有效，kl_coef、learning_rate 和 rollout 数量都会影响结果。

3. 再突出 reward_v2 的贡献。  
reward_v2 是从原始 reward 到有效 PPO 的关键改进，能够提供更密集的执行反馈。

4. 最后说明 reward_v3/v3b 的负向消融。  
结构奖励虽然更复杂，但没有提高 Pass@1，说明当前小数据条件下仍应优先依赖执行测试反馈。

这样写可以缓解“数据量较少”的问题。虽然样本规模不大，但实验并不单薄，因为它包含了完整训练闭环、多个 PPO 超参数对照、不同 reward 设计对照、验证集与测试集泛化对照，以及失败实验的原因分析。
