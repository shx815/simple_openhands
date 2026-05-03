# 论文案例分析与最终复跑计划

本文档记录论文正式撰写前需要补充的案例分析和 best PPO 最终复跑步骤。

## 1. 目标

本阶段不再扩大训练规模，重点补齐论文实验分析需要的材料：

- 对比 Base、SFT、PPO 的输出差异
- 解释 PPO 修复了哪些样例，以及在哪些样例上发生退化
- 最终复跑一次 best PPO，确认核心指标稳定

## 2. 需要保留的最终评测文件

服务器上建议保留以下目录：

| 目录 | 用途 |
|---|---|
| outputs/final_rerun_base_valid | Base 在 rl_valid 上的最终复跑结果 |
| outputs/final_rerun_sft_valid | SFT 在 rl_valid 上的最终复跑结果 |
| outputs/final_rerun_bestppo_valid | best PPO 在 rl_valid 上的最终复跑结果 |
| outputs/final_rerun_base_humaneval | Base 在 rl_test_humaneval 上的最终复跑结果 |
| outputs/final_rerun_sft_humaneval | SFT 在 rl_test_humaneval 上的最终复跑结果 |
| outputs/final_rerun_bestppo_humaneval | best PPO 在 rl_test_humaneval 上的最终复跑结果 |
| outputs/case_analysis_valid.md | valid 上的 Base/SFT/PPO 案例分析 |
| outputs/case_analysis_humaneval.md | HumanEval 上的 Base/SFT/PPO 案例分析 |

每个评测目录中至少应保留：

- summary.json
- scored_rollouts.jsonl

## 3. 服务器最终复跑命令

进入项目目录并激活环境：

```bash
cd /root/autodl-tmp/work/simple_openhands
source .venv/bin/activate
export HF_ENDPOINT=https://hf-mirror.com
export HF_HOME=/root/autodl-tmp/.cache/huggingface
export HUGGINGFACE_HUB_CACHE=/root/autodl-tmp/.cache/huggingface
export PYTHONPATH=.
```

### 3.1 rl_valid 三组复跑

Base：

```bash
python scripts/generate_execute_score.py \
  --input data/final/rl_valid.jsonl \
  --base-model-path /root/autodl-tmp/models/Qwen2.5-Coder-1.5B \
  --out-dir outputs/final_rerun_base_valid \
  --trust-remote-code \
  --reward-mode v2
```

SFT：

```bash
python scripts/generate_execute_score.py \
  --input data/final/rl_valid.jsonl \
  --base-model-path /root/autodl-tmp/models/Qwen2.5-Coder-1.5B \
  --adapter-path /root/autodl-tmp/work/simple_openhands/outputs/sft-qwen25-coder-15b-lora \
  --out-dir outputs/final_rerun_sft_valid \
  --trust-remote-code \
  --reward-mode v2
```

best PPO：

```bash
python scripts/generate_execute_score.py \
  --input data/final/rl_valid.jsonl \
  --base-model-path /root/autodl-tmp/models/Qwen2.5-Coder-1.5B \
  --adapter-path /root/autodl-tmp/work/simple_openhands/outputs/ppo_policy_update_valid_exp1_reward_v2 \
  --out-dir outputs/final_rerun_bestppo_valid \
  --trust-remote-code \
  --reward-mode v2
```

### 3.2 rl_test_humaneval 三组复跑

Base：

```bash
python scripts/generate_execute_score.py \
  --input data/final/rl_test_humaneval.jsonl \
  --base-model-path /root/autodl-tmp/models/Qwen2.5-Coder-1.5B \
  --out-dir outputs/final_rerun_base_humaneval \
  --trust-remote-code \
  --reward-mode v2
```

SFT：

```bash
python scripts/generate_execute_score.py \
  --input data/final/rl_test_humaneval.jsonl \
  --base-model-path /root/autodl-tmp/models/Qwen2.5-Coder-1.5B \
  --adapter-path /root/autodl-tmp/work/simple_openhands/outputs/sft-qwen25-coder-15b-lora \
  --out-dir outputs/final_rerun_sft_humaneval \
  --trust-remote-code \
  --reward-mode v2
```

best PPO：

```bash
python scripts/generate_execute_score.py \
  --input data/final/rl_test_humaneval.jsonl \
  --base-model-path /root/autodl-tmp/models/Qwen2.5-Coder-1.5B \
  --adapter-path /root/autodl-tmp/work/simple_openhands/outputs/ppo_policy_update_valid_exp1_reward_v2 \
  --out-dir outputs/final_rerun_bestppo_humaneval \
  --trust-remote-code \
  --reward-mode v2
```

## 4. 自动生成案例分析

复跑完成后，使用新增脚本生成案例分析草稿。

valid：

```bash
python scripts/analyze_eval_cases.py \
  --base outputs/final_rerun_base_valid/scored_rollouts.jsonl \
  --sft outputs/final_rerun_sft_valid/scored_rollouts.jsonl \
  --ppo outputs/final_rerun_bestppo_valid/scored_rollouts.jsonl \
  --out outputs/case_analysis_valid.md \
  --limit 5
```

HumanEval：

```bash
python scripts/analyze_eval_cases.py \
  --base outputs/final_rerun_base_humaneval/scored_rollouts.jsonl \
  --sft outputs/final_rerun_sft_humaneval/scored_rollouts.jsonl \
  --ppo outputs/final_rerun_bestppo_humaneval/scored_rollouts.jsonl \
  --out outputs/case_analysis_humaneval.md \
  --limit 5
```

生成后需要人工补充每个样例的分析文字，重点看：

- 是否入口函数名正确
- 是否代码可执行
- 是否有 markdown 或解释性文本污染
- 是否边界条件错误
- 是否返回类型错误
- 是否只通过部分测试
- PPO 是否修复了 SFT 的错误
- PPO 是否牺牲了 SFT 原本正确的样例

## 5. 论文建议选取的案例类型

至少选 3 类：

1. PPO 修复 SFT 的样例  
用于说明执行反馈确实能带来局部改进。

2. PPO 相比 SFT 退化的样例  
用于说明 PPO 存在泛化不足或策略偏移问题。

3. Base、SFT、PPO 都失败或都成功的样例  
用于说明模型能力边界，避免只挑有利样例。

如果篇幅允许，可以再加一类：

4. Base 正确但 SFT/PPO 错误的样例  
用于说明小样本 SFT 和 PPO 可能损伤强基座模型已有能力。

## 6. 结果回填位置

最终复跑完成后，需要更新：

- EXPERIMENT_RESULTS_TABLE.md
- EXPERIMENT_ABLATION_ANALYSIS.md
- FINAL_EXPERIMENT_CONCLUSION.md
- EXPERIMENT_SUMMARY_2026-04-30.md

如果复跑结果与当前记录只有极小差异，可以在论文中说明采用最终复跑结果，并把早期结果作为调参过程记录。
