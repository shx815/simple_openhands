# 最终实验结论

## 1. 总体结论

本课题围绕代码生成任务，构建了从数据整理、SFT 热启动到 PPO 强化学习优化的完整实验流程。实验结果表明，基于执行反馈的 PPO 方法能够在验证集上改善 SFT 后模型的表现，尤其是在引入 reward shaping 后，模型在 rl_valid 上的 Pass@1 从 SFT baseline 的 0.5714 提升到 0.6667，达到了与 Base 模型相同的 Pass@1 水平。

同时，实验也表明，所选用的 Qwen2.5-Coder-1.5B 本身已经具备较强的代码生成能力。在统一代码清洗和后处理后的评测口径下，Base 模型在 rl_valid 上的 Pass@1 已达到 0.6667，在 rl_test_humaneval 上的 Pass@1 为 0.5000。这说明强代码基座模型本身已经具备较高的初始能力，小规模 SFT 并不一定能在所有数据集上带来稳定提升。

## 2. Base、SFT 与 PPO 的对比结论

在 rl_valid 验证集上，Base、SFT 和最佳 PPO 模型的结果如下：

| 模型 | Pass@1 | average_reward |
|---|---:|---:|
| Base | 0.6667 | 0.7381 |
| SFT baseline | 0.5714 | 0.6524 |
| PPO best | 0.6667 | 0.7190 |

从验证集结果可以看出，小规模 SFT 后模型相对 Base 出现了一定下降，而 PPO 结合 reward shaping 后能够将模型的 Pass@1 从 0.5714 提升到 0.6667。这说明 PPO 能够利用执行反馈修复 SFT 后策略在验证集上的性能下降，并提升模型在当前任务分布下的解题能力。

在 rl_test_humaneval 测试集上，三组模型的结果如下：

| 模型 | Pass@1 | average_reward |
|---|---:|---:|
| Base | 0.5000 | 0.5457 |
| SFT baseline | 0.5244 | 0.5707 |
| PPO best | 0.5122 | 0.5610 |

从测试集结果可以看出，SFT 相比 Base 在 HumanEval 上取得了小幅提升，而 PPO best 略低于 SFT baseline。该结果说明当前 PPO 的增益主要体现在验证集上，尚未稳定迁移到跨数据集测试场景中。

## 3. reward shaping 的作用

实验中发现，原始 reward 仅基于测试通过比例，信号相对稀疏。在该设置下，PPO 虽然能够带来一定提升，但提升幅度有限。为增强奖励信号，本课题引入了 reward shaping：

- 代码可执行时给予 0.1 奖励
- 按测试通过比例给予 0.8 * pass_ratio 奖励
- 全部测试通过时额外给予 0.1 奖励

在新的 reward 口径下，PPO 的验证集表现明显提升。最佳 PPO 模型 exp1_reward_v2 在 rl_valid 上达到：

- Pass@1 = 0.6667
- average_reward = 0.7190

相比 SFT baseline：

- Pass@1 从 0.5714 提升到 0.6667
- average_reward 从 0.6524 提升到 0.7190

这说明 reward shaping 对当前 PPO 训练非常关键。更密集的 reward 信号能够帮助模型区分代码可执行、部分测试通过和全部测试通过等不同层次的输出质量，从而提供比原始 reward 更稳定的优化方向。

在此基础上，本课题进一步尝试了更复杂的结构奖励 reward_v3 和 reward_v3b。reward_v3 引入 AST 结构相似度和函数签名匹配奖励，reward_v3b 在此基础上降低结构奖励权重并提高测试通过比例权重。实验结果表明，两组结构奖励的验证集 Pass@1 均为 0.5952，低于 reward_v2 的 0.6667。虽然 reward_v3 的 average_reward 达到 0.7311，但没有转化为更高的测试全通过率。这说明在当前小数据和单步 PPO 设置下，代码结构相似度与最终功能正确性之间存在偏差，奖励函数并非越复杂越好。

## 4. 调参实验结论

本课题对 learning_rate、kl_coef 和 rollout 规模进行了多组对照实验。实验表明：

1. 单独降低 kl_coef 没有提升效果  
当 kl_coef 从 0.02 降到 0.01 时，模型在验证集上的 Pass@1 下降到 0.5476，说明过弱的 KL 约束会导致策略偏移过大。

2. 单独降低 learning_rate 可以提升稳定性，但不一定最优  
当 learning_rate 从 1e-5 降到 5e-6 时，模型更新更稳定，但验证集 Pass@1 为 0.5952，仍低于 exp1。

3. 扩大 rollout 规模没有自动提升效果  
当 rollout 数量从 42 扩大到 100 后，模型表现没有超过 exp1，说明 rollout 数量需要与 update 强度和 reward 设计共同匹配。

4. reward shaping 是当前最有效的改进项  
相比直接调整 learning_rate 或 kl_coef，reward shaping 对验证集表现带来了最明显提升。

5. 结构奖励没有超过执行反馈奖励  
reward_v3 和 reward_v3b 引入 AST 相似度与函数签名匹配，但 Pass@1 均低于 reward_v2。因此，最终实验选择 reward_v2 作为主奖励函数。

因此，当前阶段最优设置为：

- rollout 数量：42
- learning_rate：1e-5
- kl_coef：0.02
- batch_size：4
- reward：reward shaping v2

## 5. 局限性分析

当前实验仍存在以下局限：

1. 泛化能力仍不足  
PPO best 在 rl_valid 上能够追平 Base，并显著超过 SFT baseline，但在 rl_test_humaneval 上未超过 SFT。这说明当前 PPO 主要提升了验证集分布内表现，跨数据集泛化能力仍有待增强。

2. 数据规模较小  
当前 SFT 和 PPO 主要基于 MBPP 训练数据，样本规模有限，且与 HumanEval 的 prompt 形式和任务分布存在差异。

3. PPO 实现仍是简化版本  
当前 PPO 使用单步 episode 形式，虽然包含 policy loss、value loss、KL penalty 和单步 advantage，但还不是完整的多步轨迹 PPO 训练框架。

4. reward 设计仍有优化空间  
reward shaping 已经显著改善验证集效果，但仍可能偏向当前数据分布。结构奖励 v3/v3b 的实验说明，简单加入 AST 相似度和签名匹配并不能直接提升 Pass@1。后续需要进一步设计更贴近语义正确性和跨数据集泛化的 reward。

## 6. 可写入论文的最终表述

综合实验结果可以得出如下结论：

本文实现了一个面向代码生成任务的 SFT + PPO 训练框架，并通过执行测试反馈构造 reward，对模型生成策略进行强化学习优化。实验表明，在 rl_valid 验证集上，PPO 结合 reward shaping 能够显著改善 SFT 后模型的表现，使 Pass@1 从 0.5714 提升至 0.6667，证明执行反馈在代码生成优化中具有实际价值。

同时，实验也表明，Qwen2.5-Coder-1.5B 作为代码专用基座模型，本身已经具备较强的代码生成能力。在统一代码清洗后的评测口径下，Base 模型在 rl_valid 上已达到 0.6667 的 Pass@1。因此，小规模 SFT 和 PPO 并不必然全面超过强基座模型，而更适合作为面向特定任务分布的策略调整方法。

在 rl_test_humaneval 测试集上，SFT baseline 的 Pass@1 为 0.5244，PPO best 的 Pass@1 为 0.5122，说明当前 PPO 方法在测试集泛化方面仍存在不足。后续工作应进一步扩大训练数据规模、引入更接近测试集分布的数据样本，并设计更稳健的 reward 机制，以提升模型的跨任务泛化能力。

此外，本文还对 reward_v3 和 reward_v3b 进行了消融实验。结果显示，加入 AST 相似度和函数签名匹配后，模型验证集 Pass@1 未能超过 reward_v2。这一结果表明，在小规模代码生成强化学习实验中，执行测试反馈仍是最直接、最可靠的奖励来源，结构相似性指标更适合作为辅助分析，而不宜在当前阶段作为主优化目标。
