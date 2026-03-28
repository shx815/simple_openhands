# 实验记录汇总（2026-03-28）

## 1. 今日目标

今天的工作主线是：

1. 完成 `Qwen2.5-Coder-1.5B` 的第一轮 `SFT`
2. 对比 `Base` 与 `SFT` 的效果差异
3. 搭建 PPO 前的“生成-执行-打分”桥接链路
4. 实现最小 PPO 更新闭环
5. 验证 PPO 更新后模型是否优于 SFT

---

## 2. 数据与实验对象

### 数据集

- `SFT train`: `data/final/sft_train.jsonl`，共 `385` 条
- `SFT valid`: `data/final/sft_valid.jsonl`，共 `42` 条
- `RL valid`: `data/final/rl_valid.jsonl`，共 `42` 条

### 模型

- 基座模型：`Qwen2.5-Coder-1.5B`
- SFT 方式：`LoRA`
- PPO 初始策略：`SFT adapter`

---

## 3. SFT 实验结果

### 3.1 训练配置

- 模型：`Qwen2.5-Coder-1.5B`
- 训练方式：`LoRA SFT`
- `max_length = 1024`
- `num_train_epochs = 5`
- `per_device_train_batch_size = 2`
- `gradient_accumulation_steps = 8`
- `learning_rate = 1e-4`
- `weight_decay = 0.01`
- `warmup_ratio = 0.05`

### 3.2 训练结果

- 最终 `eval_loss = 0.7472`
- 训练过程正常完成
- 成功产出 LoRA adapter

### 3.3 生成测试

对单题进行生成测试时，模型已经可以输出结构正确、格式正常的 Python 函数，说明：

- `SFT` 已经有效提升了“按题目格式生成代码”的能力
- 但函数逻辑仍然存在错误风险，说明后续 `PPO` 仍然有必要

---

## 4. Base vs SFT A/B 测试

### 4.1 初始小规模结果

在 `rl_valid` 上做 A/B 对比时，得到：

- `Base Pass@1 = 0/42 = 0.0`
- `SFT Pass@1 = 3/42 = 7.14%`
- 绝对提升：`+7.14%`

这一结果说明：

- 小样本 `SFT` 对模型有正向帮助
- 但提升幅度有限
- 当前 `SFT` 更适合作为 PPO 的热启动模型，而非最终最优模型

### 4.2 后续统一评测口径后的更稳定结果

在后续统一 `entry_point` 对齐逻辑后，使用同一口径重新评测 `SFT` 模型，在 `rl_valid` 全量 42 条上得到：

- `full_pass_records = 24`
- `Pass@1 = 0.5714`
- `average_reward = 0.619`
- `generation_execution_failures = 0`

该结果可以视为当前 `SFT` 模型的主要 baseline。

---

## 5. PPO 前桥接链路

### 5.1 已完成模块

今天已经补齐并打通了以下组件：

- `scripts/generate_execute_score.py`
- `simple_openhands/rl/bridge.py`
- `scripts/ppo_rollout_loop.py`
- `scripts/ppo_update.py`
- `simple_openhands/rl/ppo.py`

### 5.2 当前 PPO 前半闭环能力

已经具备以下能力：

1. 输入 `prompt`
2. 策略模型生成代码
3. 本地执行 `test_code`
4. 按测试通过比例计算 `reward`
5. 记录 `old_logprob`
6. 计算 `advantage / return`

也就是说，`prompt -> generation -> execution -> reward -> rollout` 这条链已经通了。

---

## 6. PPO rollout smoke test

### 6.1 初始版本

在未做 `entry_point` 对齐前，rollout 结果较差：

- `pass_at_1 = 0.0`
- `average_reward = 0.1`

主要问题是：

- 模型生成的函数名和测试要求的 `entry_point` 不一致
- 导致大量 `NameError`
- 这些样本被误记为低 reward

### 6.2 加入 entry_point 对齐后

在加入自动别名逻辑后，`10` 条 smoke test 结果显著改善：

- `pass_at_1 = 0.4`
- `average_reward = 0.5`

这说明：

- rollout/reward 链路本身是可用的
- `entry_point` 对齐对于奖励信号质量影响非常大

---

## 7. PPO 更新实验

### 7.1 最小 PPO 更新版

先实现了最小版 PPO 更新：

- clipped policy loss
- 使用 `old_logprob`
- 单次 optimizer step

后续又升级为：

- `policy loss`
- `value head`
- 单步 `GAE / return`
- 相对 base model 的 `KL penalty`

### 7.2 单步 PPO smoke test 输出

一次更新中，控制台输出示例：

- `epoch=1 batch=1 total_loss=8.404384 policy_loss=-0.165557 value_loss=0.514882 kl_loss=416.000000 avg_ratio=0.886163`
- `epoch=1 batch=2 total_loss=5.680645 policy_loss=-1.360502 value_loss=4.832294 kl_loss=232.000000 avg_ratio=0.946873`
- `epoch=1 batch=3 total_loss=3.746486 policy_loss=-0.406465 value_loss=0.055903 kl_loss=207.000000 avg_ratio=1.249993`

最终汇总：

- `mean_total_loss = 5.943838`
- `mean_policy_loss = -0.644175`
- `mean_value_loss = 1.801026`
- `mean_kl_loss = 285.0`
- `mean_ratio = 0.983213`
- `mean_old_value = -0.252696`

### 7.3 现阶段判断

说明以下几点：

1. `PPO` 更新已经**工程上跑通**
2. `policy loss / value loss / kl loss` 都已经能正常参与计算
3. 当前最可疑的问题是：`KL` 项数值明显偏大

---

## 8. PPO 更新前后效果对比

### 8.1 统一评测口径后的全量结果

在 `rl_valid` 全量 `42` 条样本上，对更新前后的模型做同口径对比：

#### PPO 更新前（SFT adapter）

- `full_pass_records = 24`
- `Pass@1 = 0.5714`
- `average_reward = 0.619`
- `generation_execution_failures = 0`

#### PPO 更新后（ppo_policy_update_smoke_v2）

- `full_pass_records = 23`
- `Pass@1 = 0.5476`
- `average_reward = 0.5714`
- `generation_execution_failures = 0`

### 8.2 当前结论

这说明：

- 当前这轮 PPO 更新**没有带来提升**
- 并且出现了**轻微退化**
- 但退化幅度不大，说明：
  - PPO 并没有把模型彻底训坏
  - 当前主要问题更像是**超参设置不合适**

因此，现在项目已经从“工程打通阶段”转入“实验调参阶段”。

---

## 9. 当前阶段结论

### 已明确完成

- 数据准备完成
- `SFT` 第一轮完成
- `SFT` baseline 已建立
- PPO 前半闭环完成
- 最小 PPO 更新完成
- 带 `value / GAE / KL` 的单步 PPO 版本完成

### 当前最准确的项目定位

当前项目不是“还在搭框架”，而是：

**已经拥有可运行的单步 PPO 实验框架，但当前配置尚未带来性能增益，需要进入系统调参阶段。**

---

## 10. 下一轮调参建议

### 10.1 调参目标

目标不是再证明 PPO 能跑，而是：

- 让 `PPO after` 至少不低于 `SFT baseline`
- 争取在 `Pass@1` 或 `average_reward` 上得到可复现提升

### 10.2 最优先调的参数

#### 1. `kl_coef`

优先级最高。

原因：

- 当前 `mean_kl_loss = 285.0` 明显偏大
- 说明 KL 项很可能在过度约束策略更新
- 这会让 PPO 学不到有效改进，甚至把已有能力压回去

建议：

- 先尝试更小的 `kl_coef`
- 保持其他条件不变
- 看更新后 `Pass@1 / average_reward` 是否回升

#### 2. `learning_rate`

当前使用 `1e-5`，虽然不算大，但在小 rollout 场景下仍可能造成不稳定更新。

建议：

- 试更保守的一档
- 和当前值做对照

#### 3. rollout 数量

当前 smoke test 的 rollout 太少。

建议：

- 不要只用 `10` 条
- 下一轮至少扩大到：
  - `rl_valid` 全量 `42` 条
  - 或 `rl_train` 抽样 `50-100` 条

### 10.3 暂时不建议优先大改的内容

先不要急着：

- 重写 PPO 主体
- 改 reward 大结构
- 加入太多新模块

因为当前主要矛盾已经很清楚：

- 问题不在“能不能跑”
- 而在“这组超参是否合理”

### 10.4 建议的下一轮实验顺序

1. 固定当前评测口径
2. 只调 `kl_coef`
3. 做 PPO 更新
4. 跑 `rl_valid` 全量评测
5. 比较更新前后：
   - `Pass@1`
   - `average_reward`

如果这一轮仍无提升，再继续调：

- `learning_rate`
- rollout 规模

### 10.5 下一轮实验最小建议

建议你下一轮做一个最小对照实验表：

- 实验 A：当前配置
- 实验 B：减小 `kl_coef`
- 实验 C：减小 `kl_coef` + 调整 `learning_rate`

每轮都只比较：

- `Pass@1`
- `average_reward`

这样最容易看清 PPO 是否真正开始带来增益。

---

## 11. 一句话总结

今天已经完成了从 `SFT baseline` 到 `单步 PPO 更新` 的完整闭环搭建。当前系统已经具备正式做 PPO 调参实验的条件，但第一轮 PPO 更新结果显示轻微退化，因此下一阶段的工作重点应转向以 `kl_coef`、`learning_rate` 和 rollout 规模为核心的系统调参。
