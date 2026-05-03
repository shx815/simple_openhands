# 实验部分待完成事项

## 1. 补充测试集最终评测

状态：已完成。

目标：

- 使用当前最佳 PPO 模型在 rl_test_humaneval 上做最终评测
- 同时保留 SFT baseline 在同一测试集上的结果
- 得到可以直接写进论文终稿的测试集对比结论

完成标准：

- 产出 SFT 在 rl_test_humaneval 上的 summary.json
- 产出 Best PPO 在 rl_test_humaneval 上的 summary.json
- 明确记录 Pass@1 和 average_reward 对比

## 2. 整理标准对照结果表

状态：已完成。结果见 EXPERIMENT_RESULTS_TABLE.md。

目标：

- 将目前所有关键实验结果整理为统一对照表
- 形成论文实验章节中的核心表格

建议纳入的实验组：

- Base
- SFT baseline
- PPO 原始 reward exp1
- PPO reward shaping exp1_reward_v2
- PPO reward shaping exp2_reward_v2_lr5e6

完成标准：

- 每组实验都有统一字段：
  - 数据集
  - rollout 数量
  - learning_rate
  - kl_coef
  - Pass@1
  - average_reward
- 表格可直接用于论文正文

## 3. 整理消融实验与原因分析

状态：已完成。分析见 EXPERIMENT_ABLATION_ANALYSIS.md。

目标：

- 对已经做过的调参实验给出解释性分析
- 不只记录结果，还要说明为什么变好或变差

重点分析对象：

- exp1
- exp2
- exp3
- exp4
- exp5
- exp1_reward_v2
- exp2_reward_v2_lr5e6

完成标准：

- 形成文字分析，明确以下几点：
  - 为什么单独降低 kl_coef 效果不好
  - 为什么更大 rollout 没有自动更好
  - 为什么 reward shaping 明显有效
  - 为什么当前最佳结果出现在 exp1_reward_v2

## 4. 补齐论文终稿可直接引用的最终实验结论

状态：已完成。结论见 FINAL_EXPERIMENT_CONCLUSION.md。

目标：

- 将验证集和测试集结果收束成论文终稿可直接引用的实验结论
- 明确本文方法相比 baseline 的最终提升幅度

完成标准：

- 形成一段正式文字，总结：
  - SFT 相比 Base 的提升
  - PPO 相比 SFT 的提升
  - reward shaping 对 PPO 的作用
  - 当前方案的局限性与后续改进方向

## 推荐执行顺序

1. 先做测试集最终评测
2. 再整理标准对照结果表
3. 再写消融分析
4. 最后形成论文终稿实验结论

## 5. 论文正式撰写前补强事项

状态：进行中。

目标：

- 补齐论文实验章节中最容易被问到的复现性和解释性材料
- 不再盲目扩大训练规模，而是围绕已有实验结果做严谨整理
- 最终再复跑一次 best PPO，确认核心指标稳定

待完成事项：

- [x] 整理数据集统计表，记录 train/valid/test 数量、来源、用途和字段格式
- [x] 整理实验配置表，记录基座模型、SFT、PPO、reward、硬件环境等关键设置
- [ ] 做失败案例分析，对比 Base、SFT、PPO 的输出差异和失败原因
- [ ] 在服务器上最终复跑一次 best PPO 的 rl_valid 和 rl_test_humaneval 测评
- [ ] 将最终复跑结果回填到实验结果表和论文结论文档

完成标准：

- 数据集统计和实验配置可直接写入论文实验设置章节
- 案例分析至少包含 3 类样例：
  - PPO 修复 SFT 的样例
  - PPO 相比 SFT 退化的样例
  - Base、SFT、PPO 都失败或都成功的代表样例
- best PPO 最终复跑结果需要保存 summary.json 和 scored_rollouts.jsonl
