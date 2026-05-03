# 消融实验与原因分析

## 1. 分析目标

本部分的目标不是简单罗列实验结果，而是解释以下问题：

1. 为什么 PPO 在部分设置下优于 SFT baseline
2. 为什么某些超参数调整会导致性能退化
3. 为什么 reward shaping 能显著提升效果
4. 为什么验证集与测试集结果存在差异

本文将围绕以下实验组进行分析：

- PPO exp1
- PPO exp2
- PPO exp3
- PPO exp4
- PPO exp5
- PPO exp1_reward_v2
- PPO exp2_reward_v2_lr5e6
- PPO exp1_reward_v3
- PPO exp1_reward_v3b

## 2. 基线回顾

在统一代码清洗后的最终评测口径下，Base 在验证集 rl_valid 上的结果为：

- Pass@1 = 0.6667
- full_pass_records = 28/42
- average_reward = 0.7381

在进行 PPO 之前，SFT baseline 在验证集 rl_valid 上的结果为：

- Pass@1 = 0.5714
- full_pass_records = 24/42
- average_reward = 0.6524

这说明：

- Qwen2.5-Coder-1.5B 本身已经具备较强代码生成能力
- 小样本 SFT 并没有在 valid 上超过 Base
- PPO 的主要作用是修复 SFT 后策略在 valid 上的下降，并将其拉回到 Base 水平

## 3. 原始 reward 条件下的 PPO 消融分析

### 3.1 exp1：原始 reward 下的第一组有效 PPO 结果

exp1 配置：

- rollout 数量：42
- learning_rate：1e-5
- kl_coef：0.02
- batch_size：4

结果：

- Pass@1 = 0.619
- average_reward = 0.627

相对 SFT baseline，exp1 带来了小幅但明确的提升。需要注意的是，在最终强后处理口径下，exp1 仍低于 Base，因此该结果应解释为 PPO 对 SFT 后策略的修复，而不是超过强基座模型。其原因主要有以下几点：

1. rollout 规模与 update 强度处于相对平衡状态  
当前 rollout 数量虽然不大，但与单轮 PPO update 的更新强度基本匹配，因此不会出现严重过拟合或明显欠更新。

2. PPO 已经能够利用执行反馈微调输出  
在这一阶段，模型已经从单纯模仿标准答案，转向根据测试执行反馈修正生成行为，因此相比纯 SFT 获得了小幅提升。

3. reward 虽然较稀疏，但仍能提供有效方向  
尽管原始 reward 仅基于通过比例，信号偏稀疏，但在较小 rollout 场景下仍然足以支撑一次有效更新。

因此，exp1 是原始 reward 条件下第一组优于 baseline 的 PPO 结果。

### 3.2 exp2：单独降低 kl_coef 的退化

exp2 配置：

- rollout 数量：42
- learning_rate：1e-5
- kl_coef：0.01
- batch_size：4

结果：

- Pass@1 = 0.5476
- average_reward = 0.5794
- mean_ratio = 1.957645

该实验明显劣于 exp1，原因可以归纳为：

1. 降低 kl_coef 后，策略偏移过大  
从 mean_ratio 接近 2 可以看出，当前策略相对旧策略的偏移明显增大。这意味着 PPO 更新缺少足够约束，导致策略走得过远。

2. KL 项虽然系数减小，但整体并未变得更稳定  
本意是希望减弱 KL 约束后提升探索性，但在当前实现和数据规模下，较弱的约束反而放大了更新不稳定性。

3. 原始 reward 信号较稀疏，较大的策略偏移更容易造成性能退化  
当 reward 本身不够密时，过大的更新更容易让模型偏离已有的 SFT 通用能力，而不能稳定积累正确行为。

结论：

- 单独降低 kl_coef 不是当前实现下的有效方向

### 3.3 exp3：降低 learning_rate 后更稳但不最优

exp3 配置：

- rollout 数量：42
- learning_rate：5e-6
- kl_coef：0.02
- batch_size：4

结果：

- Pass@1 = 0.5952
- average_reward = 0.619
- mean_ratio = 1.005761

exp3 相比 exp2 更稳定，也优于 baseline，但仍不如 exp1。其原因如下：

1. 降低 learning_rate 后，参数更新幅度明显减小  
从 mean_ratio 接近 1 可以看出，策略更新更保守，不会像 exp2 那样发生过强偏移。

2. 更新更稳，但收益也被压缩  
学习率降低后，虽然减少了退化风险，但同时也削弱了 PPO 从执行反馈中提取收益的能力，因此没有超过 exp1。

3. 当前 rollout 规模较小  
在 42 条样本条件下，1e-5 的学习率仍然是可控的。过早降到 5e-6，反而可能使更新过弱。

结论：

- 较小 learning_rate 能增加稳定性
- 但在当前小 rollout 场景下，过度保守会牺牲收益

### 3.4 exp4 与 exp5：扩大 rollout 规模未带来收益

exp4 配置：

- rollout 数量：100
- learning_rate：1e-5
- kl_coef：0.02
- batch_size：4

结果：

- Pass@1 = 0.5714
- average_reward = 0.6111

exp5 配置：

- rollout 数量：100
- learning_rate：5e-6
- kl_coef：0.02
- batch_size：4

结果：

- Pass@1 = 0.5714
- average_reward = 0.6032

这两组实验共同说明：

1. 更大的 rollout 规模并没有自动转化为更好性能  
这表明 PPO 不是简单地“样本越多越好”，而是 rollout 规模、reward 设计与 update 强度需要一起匹配。

2. 当前实现仍属于单步 PPO 近似版本  
在这种实现下，更大的 rollout 会带来更复杂的样本分布。如果 value、KL 和 advantage 估计还不够成熟，更大样本未必能稳定转化为正收益。

3. 100 条 rollout 可能超出了当前 update 设置的最佳匹配范围  
无论保持 1e-5 还是降到 5e-6，结果都未超过 exp1，说明当前系统的最佳点并不在更大 rollout 上。

结论：

- rollout 规模不是越大越好
- 在当前实现下，较小 rollout 反而更适合当前 PPO update 结构

## 4. reward shaping 的作用分析

reward shaping 是本轮实验最关键的改进。

新的 reward 规则为：

- 代码可执行：奖励 0.1
- 测试通过比例：奖励 0.8 * pass_ratio
- 全部测试通过：额外奖励 0.1

### 4.1 为什么 reward shaping 有效

1. reward 变得更密集  
原始 reward 主要依赖测试通过比例，导致很多样本即使代码接近正确，也只能获得很弱的反馈。新 reward 至少为“可执行”提供了正向信号，使策略能够更早学习到基本代码结构。

2. reward 更符合代码生成任务的层次结构  
代码生成任务不是简单的对错二分类，而是具有明显的层级：
- 先保证代码可执行
- 再保证部分测试通过
- 最后追求全部测试通过  
reward shaping 使 PPO 更容易利用这种层级信息。

3. 改善了 PPO 的优化方向  
在原始 reward 下，PPO 可能主要围绕少量高 reward 样本更新，容易受噪声影响。新 reward 为更多样本提供了区分度，使更新方向更稳定。

### 4.2 exp1_reward_v2：当前最佳结果

配置：

- rollout 数量：42
- learning_rate：1e-5
- kl_coef：0.02
- batch_size：4
- 使用 reward shaping

结果：

- Pass@1 = 0.6667
- average_reward = 0.719

这是当前最佳结果，其原因可以总结为：

1. reward 密度提高后，PPO 可以更有效地区分样本优劣  
相比原始 reward，更多样本提供了有意义的梯度方向。

2. rollout 规模仍保持在当前实现可稳定吸收的范围  
42 条 rollout 在当前实现下已经足够提供有效反馈，同时又不会像 100 条那样带来额外不稳定性。

3. learning_rate 与 kl_coef 的组合恰好匹配新的 reward 口径  
在 reward 更密集后，原本的 1e-5 学习率不再显得过激，反而能更充分地利用新 reward 信号。

结论：

- reward shaping 与当前 PPO update 结构是匹配的
- 这也是本轮实验取得最佳结果的核心原因

### 4.3 exp2_reward_v2_lr5e6：进一步降低 learning_rate 后的退化

配置：

- rollout 数量：42
- learning_rate：5e-6
- kl_coef：0.02
- batch_size：4
- 使用 reward shaping

结果：

- Pass@1 = 0.619
- average_reward = 0.6762

虽然该实验仍优于旧 baseline，但不如 exp1_reward_v2。其原因是：

1. reward shaping 已经提供更强的有效信号  
在信号变强后，过度降低 learning_rate 反而会削弱 PPO 对有益信号的吸收能力。

2. 当前更新强度已经不需要再进一步保守  
在 reward shaping 条件下，原本的 1e-5 已经能够在较好平衡收益与稳定性之间工作，因此 5e-6 反而过弱。

结论：

- reward shaping 后，1e-5 比 5e-6 更适合当前 PPO update

### 4.4 reward_v3 与 reward_v3b：结构奖励没有带来 Pass@1 增益

在参考执行反馈强化学习相关工作的基础上，本课题进一步尝试了更复杂的奖励函数设计。reward_v3 在 reward_v2 的基础上加入 AST 结构相似度和函数签名匹配奖励，希望模型不仅通过测试，还能生成更接近参考答案结构的代码。其主要组成包括：

- 代码可执行奖励
- 入口函数存在奖励
- AST 结构相似度奖励
- 函数签名匹配奖励
- 测试通过比例奖励
- 全部测试通过奖励

reward_v3 的结果为：

- Pass@1 = 0.5952
- full_pass_records = 25/42
- average_reward = 0.7311

可以看到，reward_v3 的 average_reward 高于 reward_v2，但 Pass@1 明显低于 reward_v2 的 0.6667。这说明结构奖励提高了总 reward 数值，但并没有同步提高最终测试全通过率。其核心原因是 AST 相似度和函数签名匹配属于代理指标，它们能衡量代码形态是否接近参考答案，却不能保证代码语义正确。

为了降低结构奖励对 PPO 优化方向的干扰，本课题进一步设置 reward_v3b，降低 AST 相似度和函数签名奖励权重，并提高测试通过比例的权重。reward_v3b 的结果为：

- Pass@1 = 0.5952
- full_pass_records = 25/42
- average_reward = 0.6749

reward_v3b 的 average_reward 下降，说明结构奖励的过度加分得到缓解，但 Pass@1 仍未超过 reward_v2。因此，在当前数据规模和单步 PPO 实现下，更复杂的结构奖励并没有带来实际性能提升。

该实验可以作为论文中的负向消融结果：奖励函数并非越复杂越好。对于小数据代码生成任务，最终测试通过率仍然是最可靠的优化目标，结构相似度只能作为辅助分析指标，不适合作为当前 PPO 主奖励。

## 5. 验证集与测试集差异分析

当前最佳结果 exp1_reward_v2 在验证集上的表现为：

- Pass@1 = 0.6667
- average_reward = 0.719

Base 在验证集上的表现为：

- Pass@1 = 0.6667
- average_reward = 0.7381

但在 HumanEval 测试集上的表现为：

- Pass@1 = 0.5122
- average_reward = 0.5610

而 SFT baseline 在 HumanEval 测试集上为：

- Pass@1 = 0.5244
- average_reward = 0.5707

Base 在 HumanEval 测试集上为：

- Pass@1 = 0.5000
- average_reward = 0.5457

这说明：

1. PPO 的主要收益体现在验证集，而未能迁移到测试集  
这说明当前 PPO 更像是在当前训练/验证分布上做局部优化，而不是稳定提升跨数据集泛化能力。

2. reward shaping 提升了验证集上相对 SFT 的性能，但没有自动改善测试集泛化  
新的 reward 设计更适合优化当前数据分布下的目标，但仍然无法完全弥补训练集与测试集之间的分布差异。

3. 测试集表现略低于 SFT baseline  
这表明当前 PPO 仍可能牺牲一部分原有的通用能力，以换取在验证集上的更高得分。

结论：

- 当前 PPO 已经证明在验证集上有效
- 但测试集结果说明模型泛化能力仍然不足
- 后续若继续优化，应优先关注训练分布、reward 设计与泛化能力之间的平衡

## 6. 综合结论

通过本轮消融实验可以得出以下结论：

1. PPO 在当前项目中对 SFT 后策略是有效的，但有效性依赖于合理的 reward 设计和合适的 update 强度。

2. 单独降低 kl_coef 并不能改善结果，反而会加剧策略偏移。

3. 单独降低 learning_rate 可以提升稳定性，但不一定带来最优性能。

4. 更大的 rollout 规模并不天然更优，当前实现下 42 条 rollout 比 100 条 rollout 更适合。

5. reward shaping v2 是本轮实验中最有效的改进手段，它显著提升了 PPO 在验证集上的表现。

6. reward_v3 和 reward_v3b 的结果说明，AST 相似度和函数签名等结构奖励虽然能提高或调整 reward 数值，但没有带来 Pass@1 增益，因此最终不作为主实验设置。

7. 当前最佳结果出现在 exp1_reward_v2，说明在较小 rollout、适中 learning_rate 与更密执行反馈 reward 组合下，PPO 能够稳定优于 SFT baseline，并在 valid 的 Pass@1 上追平 Base。

8. 测试集结果表明，当前方法的主要瓶颈已经从“训练闭环是否可行”转向“泛化能力是否足够”。
