# 下次上机完整实验计划

## 目标

下次上机的目标不是继续搭框架，而是尽量一次完成当前课题所需的主要实验部分，包括：

1. 恢复服务器环境并同步最新代码
2. 固定当前 SFT baseline
3. 完成一轮系统性的 PPO 调参实验
4. 获得 PPO 更新前后对比数据
5. 整理实验结果文件，便于后续写中期检查、论文和答辩材料

一句话概括：  
下次上机要把“PPO 能不能真正提升性能”这件事尽量做出明确结论，并把结果保存完整。

补充说明：  
之前使用的服务器实例已经被释放，因此下次上机不能默认依赖旧实例中的代码、模型、虚拟环境和 outputs 目录。下次上机应按“新机器恢复”的思路执行，即先恢复代码和实验环境，再继续 PPO 实验。

---

## 一、上机前准备

### 1. 本地准备

上机前先在本地确认以下内容已经齐全：

- 代码已 push 到远端 dev 分支
- 本地保留以下文档：
  - `plan.md`
  - `TASK_PROGRESS.md`
  - `EXPERIMENT_SUMMARY_2026-03-28.md`
  - `simple_openhands/midterm_report.md`
- 本地已有之前服务器实验产物备份

此外，还应确认本地已经保留以下内容，因为下次新服务器恢复会直接依赖它们：

- 基础代码仓库最新版本
- SFT 训练得到的 adapter 备份
- PPO rollout / update / compare 等历史实验结果备份
- 实验总结文档与中期检查材料

### 2. 明确本次实验目标

这次上机只围绕 PPO 正式实验，不再做以下工作：

- 不再重新整理数据
- 不再重新写 SFT 训练脚本
- 不再重新搭基础执行环境
- 不再大改总体架构

本次只做：

- 恢复环境
- 跑 PPO 调参实验
- 做全量对比评测
- 记录结果

### 3. 新服务器恢复原则

由于旧实例已释放，下次上机要默认以下内容都需要重新检查或重新准备：

- 服务器规格是否满足当前实验需求
- 项目代码是否重新 clone
- Python 虚拟环境是否重新创建
- 训练依赖是否重新安装
- 基座模型是否重新下载
- SFT adapter 和已有实验产物是否需要重新上传

因此，下次上机的第一优先级不是直接开始 PPO，而是先把实验恢复到“和上次离开时等价”的状态。

---

## 二、上机后第一阶段：恢复环境

这一阶段默认基于“新租服务器、旧实例已释放”的前提设计。

### 1. 登录服务器

```bash
ssh -p 26939 root@connect.cqa1.seetacloud.com
```

### 2. 进入项目目录

如果是新服务器，先创建工作目录：

```bash
mkdir -p /root/autodl-tmp/work
cd /root/autodl-tmp/work
```

然后再进入项目目录。

如果项目目录还不存在，执行：

```bash
git clone -b dev https://github.com/shx815/simple_openhands.git
cd simple_openhands
```

如果项目目录已经存在，再执行：

```bash
cd /root/autodl-tmp/work/simple_openhands
```

### 3. 同步最新代码

```bash
git checkout dev
git pull origin dev
```

### 4. 激活虚拟环境

由于旧实例已经释放，下次上机不要默认 `.venv` 一定还能用。建议按以下顺序检查：

```bash
ls -a
```

如果 `.venv` 存在且可用：

```bash
source .venv/bin/activate
```

如果 `.venv` 不存在或已损坏，则直接重建：

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install torch torchvision torchaudio
pip install transformers datasets peft accelerate sentencepiece
pip install numpy pandas scikit-learn
pip install -e .
```

### 5. 检查依赖

```bash
python -c "import torch; print(torch.__version__); print(torch.cuda.is_available())"
python -c "import transformers, peft, accelerate; print('deps ok')"
python -c "import simple_openhands; print('package ok')"
```

### 6. 检查模型与输出目录

旧实例已释放时，这一步大概率需要重新准备。

```bash
ls /root/autodl-tmp/models/Qwen2.5-Coder-1.5B
ls outputs
```

要确认这些目录还在：

- `/root/autodl-tmp/models/Qwen2.5-Coder-1.5B`
- `outputs/sft-qwen25-coder-15b-lora`
- `outputs/ppo_rollouts_valid_smoke_v2`
- `outputs/ppo_policy_update_smoke_v2`

如果这些目录缺失，就先恢复，再继续实验。

### 7. 恢复基座模型

如果模型目录不存在，先重新下载：

```bash
mkdir -p /root/autodl-tmp/models
export HF_ENDPOINT=https://hf-mirror.com
export HF_HOME=/root/autodl-tmp/.cache/huggingface
export HUGGINGFACE_HUB_CACHE=/root/autodl-tmp/.cache/huggingface

hf download Qwen/Qwen2.5-Coder-1.5B \
  --local-dir /root/autodl-tmp/models/Qwen2.5-Coder-1.5B
```

### 8. 恢复 SFT adapter 与历史实验产物

如果旧实例已释放，而本地已经备份过实验压缩包，则需要把关键产物重新传到服务器，例如：

- `outputs/sft-qwen25-coder-15b-lora`
- 需要继续复用的 PPO rollout / update 结果

推荐做法：

1. 本地先将备份压缩包通过 `scp` 上传到新服务器
2. 在服务器上解压到 `/root/autodl-tmp/work/simple_openhands/outputs/`

如果你已经决定重新跑全部实验，也可以只恢复：

- `SFT adapter`

其余 PPO 中间结果可以重新生成。

---

## 三、第二阶段：固定当前 baseline

在做任何 PPO 调参前，先重新确认当前 SFT baseline，作为后续所有实验的统一比较对象。

注意：如果这是一台新服务器，且你只恢复了 SFT adapter，没有恢复旧 PPO 中间结果，也完全没问题。只要能先把 SFT baseline 重新测出来，后续 PPO 实验仍可继续。

### 1. 重新跑 SFT baseline 评测

```bash
python scripts/generate_execute_score.py \
  --input data/final/rl_valid.jsonl \
  --base-model-path /root/autodl-tmp/models/Qwen2.5-Coder-1.5B \
  --adapter-path /root/autodl-tmp/work/simple_openhands/outputs/sft-qwen25-coder-15b-lora \
  --out-dir outputs/baseline_sft_valid_full \
  --trust-remote-code
```

### 2. 记录 baseline

查看：

```bash
cat outputs/baseline_sft_valid_full/summary.json
```

基于目前已有实验，预计 baseline 约为：

- `Pass@1 = 0.5714`
- `average_reward = 0.619`

如果新结果和这个差别很大，先暂停后续实验，检查环境和代码是否一致。

---

## 四、第三阶段：PPO 调参实验主线

当前已经知道：

- PPO 工程闭环可运行
- 当前配置会轻微退化
- 最值得优先调的是 `kl_coef`

因此下次上机的调参策略应采用“少量变量、逐轮验证”的方法。

如果新服务器恢复成本较高，建议优先保证：

1. 代码与环境可用
2. SFT baseline 已测出
3. 至少完成 2 到 3 组 PPO 调参实验

在此基础上，再决定是否扩展更多实验组。

### 总原则

1. 一次只改 1 到 2 个关键参数
2. 每组参数都跑相同的评测口径
3. 每轮实验都记录：
   - rollout summary
   - ppo update summary
   - PPO 后验证 summary

---

## 五、建议的实验分组

### 实验 A：当前配置复现实验

目的：

- 确认当前 PPO 配置的结果可重复
- 作为后续调参对照组

步骤：

1. 用当前 SFT 模型收集 rollout
2. 用当前 PPO 配置做 update
3. 对更新后模型做全量验证

需要记录：

- rollout 前 `Pass@1`
- rollout 前 `average_reward`
- PPO 后 `Pass@1`
- PPO 后 `average_reward`

### 实验 B：减小 kl_coef

目的：

- 检查 KL 惩罚过强是否是当前退化主因

建议：

- 保持其他参数不变
- 只降低 `kl_coef`

要记录：

- `mean_kl_loss` 是否下降
- PPO 后 `Pass@1` 是否提升
- PPO 后 `average_reward` 是否提升

### 实验 C：减小 kl_coef + 调整 learning_rate

目的：

- 检查当前更新幅度是否过大或方向不稳

建议：

- 在实验 B 较合理的 `kl_coef` 基础上
- 进一步调整 `learning_rate`

要观察：

- `avg_ratio` 是否更稳定
- `policy_loss` 是否更合理
- 最终评测是否优于实验 A/B

### 实验 D：扩大 rollout 样本规模

目的：

- 检查样本规模过小是否导致 PPO 更新噪声过大

建议：

- 在前面最优参数组合下
- 把 rollout 从小规模提高到：
  - `rl_valid` 全量 42 条
  - 或 `rl_train` 抽样 50-100 条

要观察：

- PPO 更新后的波动是否减小
- 结果是否比小样本 rollout 更稳定

---

## 六、每轮实验的固定执行模板

为了减少上机时混乱，建议每轮实验严格按以下模板执行。

### 第一步：收集 rollout

```bash
python scripts/ppo_rollout_loop.py \
  --input data/final/rl_valid.jsonl \
  --base-model-path /root/autodl-tmp/models/Qwen2.5-Coder-1.5B \
  --adapter-path /root/autodl-tmp/work/simple_openhands/outputs/sft-qwen25-coder-15b-lora \
  --out-dir outputs/EXP_NAME_rollouts \
  --trust-remote-code
```

### 第二步：执行 PPO update

```bash
python scripts/ppo_update.py \
  --input outputs/EXP_NAME_rollouts/rollouts.jsonl \
  --base-model-path /root/autodl-tmp/models/Qwen2.5-Coder-1.5B \
  --adapter-path /root/autodl-tmp/work/simple_openhands/outputs/sft-qwen25-coder-15b-lora \
  --out-dir outputs/EXP_NAME_update \
  --trust-remote-code \
  --epochs 1 \
  --batch-size 4 \
  --learning-rate XXXX \
  --clip-eps 0.2 \
  --kl-coef XXXX
```

### 第三步：评测 PPO 更新后模型

```bash
python scripts/generate_execute_score.py \
  --input data/final/rl_valid.jsonl \
  --base-model-path /root/autodl-tmp/models/Qwen2.5-Coder-1.5B \
  --adapter-path /root/autodl-tmp/work/simple_openhands/outputs/EXP_NAME_update \
  --out-dir outputs/EXP_NAME_eval \
  --trust-remote-code
```

### 第四步：记录三个 summary

每轮实验至少保存以下三个文件：

- `outputs/EXP_NAME_rollouts/summary.json`
- `outputs/EXP_NAME_update/ppo_update_summary.json`
- `outputs/EXP_NAME_eval/summary.json`

---

## 七、建议的实验命名规范

为了后续整理，建议统一使用如下命名方式：

- `ppo_exp_a_current`
- `ppo_exp_b_lowkl`
- `ppo_exp_c_lowkl_lowlr`
- `ppo_exp_d_more_rollouts`

对应目录命名示例：

- `outputs/ppo_exp_a_current_rollouts`
- `outputs/ppo_exp_a_current_update`
- `outputs/ppo_exp_a_current_eval`

这样后面整理数据时不会混乱。

---

## 八、本次上机预期至少完成的实验

如果时间正常，建议至少完成以下内容：

1. SFT baseline 全量确认
2. 实验 A：当前配置复现
3. 实验 B：降低 kl_coef
4. 实验 C：降低 kl_coef + 调 learning_rate

如果还有时间，再做：

5. 实验 D：扩大 rollout 规模

---

## 九、每轮实验要记录的指标

每一轮实验建议统一整理以下指标：

### 1. rollout 指标

- `pass_at_1`
- `average_reward`
- `average_advantage`

### 2. PPO update 指标

- `mean_total_loss`
- `mean_policy_loss`
- `mean_value_loss`
- `mean_kl_loss`
- `mean_ratio`

### 3. 更新后评测指标

- `Pass@1`
- `average_reward`
- `generation_execution_failures`

### 4. 关键案例

每轮至少保留 2 到 3 个样本：

- PPO 前错、PPO 后对
- PPO 前对、PPO 后错
- PPO 前后都错但 reward 提升

这些案例对后面写论文和中期报告都很重要。

---

## 十、判断实验是否成功的标准

### 最低成功标准

- PPO update 能稳定运行
- 不出现明显崩溃或大规模退化
- 至少有一组参数使 PPO 后结果接近或持平 SFT baseline

### 合格成功标准

- 至少有一组参数使 PPO 后：
  - `Pass@1` 不低于 SFT baseline
  - `average_reward` 高于或接近 SFT baseline

### 理想成功标准

- 至少有一组参数使 PPO 后：
  - `Pass@1` 高于 SFT baseline
  - `average_reward` 高于 SFT baseline
  - 且结果可重复

---

## 十一、下次上机不要再做的事

为了避免浪费时间，下次上机不要优先做这些：

- 不重新整理数据
- 不重新写 SFT 脚本
- 不重新搭基础运行时
- 不盲目大改 PPO 主体
- 不同时改太多超参

核心任务是调参与拿结果，不是再开新坑。

---

## 十二、实验结束后的收尾动作

每次实验做完后，务必完成以下收尾：

1. 备份结果

至少打包 `outputs/` 中本次实验目录：

```bash
tar -czf /root/autodl-tmp/ppo_experiment_pack.tar.gz outputs
```

2. 拉回本地

用本地机器通过 `scp` 下载压缩包。

3. 同步代码

如果脚本有改动，及时：

```bash
git add ...
git commit -m "..."
git push origin dev
```

4. 更新实验记录

把本次参数和结果补到实验总结文档中，避免下次忘记。

5. 明确标记哪些文件是“必须下次恢复”的

由于实例可能再次释放，建议每次实验结束都在本地明确保留：

- 最新代码版本
- SFT adapter
- 最优 PPO update 结果
- 对应 summary 文件
- 本次实验计划和实验总结文档

---

## 十三、一句话执行摘要

下次上机的核心任务是：在现有可运行的单步 PPO 框架上，通过围绕 kl_coef、learning_rate 和 rollout 规模的系统调参，完成至少三组可对比实验，最终拿到一组尽可能优于 SFT baseline 的 PPO 结果，并把实验数据与结果文件完整保存下来。

由于旧服务器实例已经释放，下次上机还必须先完成“新服务器环境恢复”这一步，包括重新拉代码、重建虚拟环境、检查依赖、恢复模型和必要实验产物，然后再进入正式实验。
