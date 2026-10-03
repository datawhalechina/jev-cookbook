# PyTRIO 自建数据微调结果

日期：2026-09-29（Asia/Shanghai）

## 数据和训练

- 来源：`AI-ModelScope/sharegpt_gpt4` 中文对话子集，v2 Laya 决策数据。
- 全集：1,900 个来源组、9,500 个字段标签；训练 1,200 组 / 6,000 字段，dev 200 / 1,000，calibration 100 / 500，test 400 / 2,000。
- 每项标签来自 DeepSeek Flash 三轮投票；人工审核表 9,500 行目前均待审核。多数票是 hard-SFT 目标，票频 soft target 只用于测量 soft CE/Brier。
- 切分按 `source_group_id` 隔离。训练只读取 train；dev 保留但本轮未用于 checkpoint 选择，固定训练 2 epoch 后评估 step 150。校准只读取 calibration。test 沿用此前 Laya 实验切分，旧实验已经看过该结果，因此不是新的盲测。
- `zh-pilot-112` 未修改。

训练：Qwen3.5-4B，PyTRIO 0.2.9，LoRA rank 32，学习率 `1e-4`，batch size 16，2 epoch，共 150 optimizer steps；SwanLab disabled。PyTRIO 托管服务实际执行参数更新，本机负责构造样本与发请求。训练耗时 316.73 秒，loss 从 step 1 的 3.5794 降到 step 150 的 0.2753（中间有正常波动）。

最终权重：`trio://run_rc3f5qm749kc/sampler_weights/pytrio-laya-v2-20260929-step-150`

## 同一 400 组 test 对比

| 方法 | Accuracy | Soft CE | Soft Brier | ECE10 | 温度 |
|---|---:|---:|---:|---:|---:|
| Train-majority baseline | 70.20% | — | — | — | — |
| Laya Head-only | 74.00% | 0.8628 | — | — | — |
| PyTRIO Base，raw | 74.35% | 0.6965 | 0.3135 | 0.0980 | 1.000 |
| Laya LoRA-SFT | 82.40% | 0.9390 | — | — | — |
| Laya RLCD-style | 82.60% | 1.9452 | — | — | — |
| PyTRIO LoRA-SFT，raw | **90.65%** | **0.2590** | **0.1126** | **0.0158** | 1.000 |
| PyTRIO LoRA-SFT，calibrated | 90.65% | 0.2584 | 0.1125 | 0.0163 | 1.0146 |

测试集共 2,000 个字段决策，hard accuracy 对照三票多数标签；soft CE/Brier 对照三票频率分布。Laya 旧结果没有留存 ECE/Brier，所以表中不补造这些指标。多数类 baseline 使用 train split 中每个字段的多数标签，在 test 上打分。

旧 Laya 数值来自本地保存的 `holdout_metrics.json`；远端归档目录没有保存 head-only、LoRA-SFT、RLCD 的 checkpoint 权重，所以本轮没有重新加载这些模型做配对推理，也无法从旧结果恢复逐字段误差或做 paired bootstrap。

PyTRIO 微调相对同一 Qwen 基座提升 16.30 个百分点；相对旧 Laya LoRA-SFT / RLCD-style 分别高 8.25 / 8.05 个百分点。soft CE 从 0.6965 降到 0.2590。这个优势是当前配置与切分下的观测值，不能归因于训练算法或模型架构中的某单一因素。

按题型汇总：

| 题型 | PyTRIO Base | PyTRIO LoRA-SFT | 旧 Laya LoRA-SFT | 旧 Laya RLCD-style |
|---|---:|---:|---:|---:|
| Choice（response_strategy + primary_domain） | 78.25% | **86.13%** | 73.13% | 73.75% |
| Boolean（clarification + external verification） | 95.50% | **96.75%** | 95.38% | 95.50% |
| Score（reasoning_depth） | 24.25% | **87.50%** | 75.00% | 74.50% |

提升主要出现在 `reasoning_depth`：基础 Qwen 倾向预测类别 `0`，微调后改为更符合多数标签分布的类别 `1`。两个 Boolean 字段存在强不平衡：test 中 `needs_clarification=true` 仅 9/400，`needs_external_verification=true` 仅 27/400。单看其约 98% / 95.5% accuracy 会高估对少数正类的识别，因此要一起查看逐字段、逐类别预测。

在 calibration 上拟合的温度约为 1.0146，非常接近 1。它让 test soft CE 仅改善 0.0006，ECE 反而从 0.0158 变成 0.0163；当前证据不支持温度缩放有实际收益。

## 架构与目标差异

- **Laya**：ModernBERT encoder（22 层、hidden size 768、12 attention heads），加 typed-decision classifier；旧实验 manifest 记录总参数 321,908,995。Head-only 冻结 encoder；LoRA-SFT 在 attention LoRA 和决策头训练；RLCD-style 全量更新 encoder 与决策头。
- **PyTRIO-Jev**：Qwen3.5-4B causal LM，通过固定符号表把每个字段答案编码成一个 token，在 JSON 答案骨架相应位置做 masked CE；本实验 LoRA rank 32。模型名约 4B 参数，规模约为 Laya 旧 encoder+head 的 12.4 倍。
- **标签目标不同**：Laya 两种 SFT 和 RLCD 旧实验以票频 soft target 为训练监督；PyTRIO 上游 masked SFT 用多数票 hard target。PyTRIO 在该小实验中分数更好，不表示 RLCD 原理不适用，也不能与软目标/硬目标的校准质量直接画等号。

## 限制和后续

1. 标签尚无人审，且来自模型投票；同一模型家族可能学到标注偏差。请先人工审核一批覆盖各字段、尤其稀有标签的样本。
2. 400 组 test 已被旧 Laya 实验查看并用于此次对照；要做可信发布，应另建按来源组隔离的新盲测集，冻结后只评估一次。
3. 未做多随机种子重复或按 conversation group bootstrap，因此未报告置信区间；同一对话的五个字段也不是完全独立观测。
4. 本轮没有使用 dev 选择 checkpoint 或早停；下一轮应在训练前固定 epoch 与选择指标，避免事后根据 test 调参。
5. PyTRIO 是约 4B 参数的生成式模型，Laya 约 322M 的 encoder/classifier；资源规模不匹配，无法据此比较参数效率。
6. 校准集只有 100 组且分布也来自同一伪标签源；温度结果仅是小样本诊断，不是概率可靠性证明。
7. ModelScope 数据卡显示 CC-BY-4.0；在公开/再分发数据或权重前，应核对 ShareGPT 上游条款及来源 attribution 要求。

建议顺序：先人工审核并冻结新的 group-held-out 测试集；随后固定任务提示与 token/schema 编码，以同一标签和数据预算复跑 Laya LoRA、PyTRIO LoRA；报告 macro/per-field accuracy、稀有类 recall、soft CE、Brier、ECE、训练资源和多 seed 区间。若研究 RLCD，再单独做软标签 CE-only / RLCD / 混合目标消融，不能直接把当前硬标签 PyTRIO SFT 作为 RLCD 对照。

## 文件

- 表格与图：`outputs/01a0cbf0-6ef3-7d12-b2ae-9ae7db0635c6/`
- 训练日志与 base/LoRA 评估 JSON：`outputs/`
- 训练/校准/test 的 JSONL 和 SHA-256：`data_generation/generated/sharegpt_zh_38k/v2/pytrio-custom-v2-20260929/manifest.json`（数据目录被 Git 忽略，权重保存在 PyTRIO 托管服务）。
