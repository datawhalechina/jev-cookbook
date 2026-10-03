# PyTRIO × Laya 自建对话决策数据微调（2026-09-29）

本实验把 ShareGPT 中文 v2 的 Laya typed-decision 候选集转换为 PyTRIO-Jev canonical 格式，在 Qwen3.5-4B 上做 masked LoRA SFT，并用同一份 400 组测试切分对比基础模型、微调模型和既有 Laya 结果。

## 数据与证据边界

- 源数据：`AI-ModelScope/sharegpt_gpt4` 中文子集；ModelScope 数据卡显示 CC-BY-4.0，重新分发前仍需核对上游 ShareGPT 条款。
- 1,900 个对话 / 9,500 个决策字段；每个字段由 DeepSeek Flash 三轮独立投票汇总。人工审核表目前全部未填写，所以标签是伪标签，不是人工金标或校准概率。
- 按原 `source_group_id` 分成 1,200 train、200 dev、100 calibration、400 test。训练只读 train；本轮固定训练 2 epoch，没有用 dev 做 checkpoint 选择；calibration 只拟合一个温度，test 只评估。
- 这份 test 已用于既有 Laya 实验并查看过结果。本实验可作同切分模型比较，不是新的盲测。没有人工审核集，因此不应据此宣称真实业务泛化。
- `zh-pilot-112` 保持原样。本目录新增的结果与它分开。

转换结果、文件哈希和标签计数保存在生成目录的 `manifest.json`。转制脚本保留软票频率供评估；PyTRIO 上游 masked SFT 使用多数票硬标签训练，优化目标与 Laya 的软标签交叉熵及 RLCD 都不同。

## 运行

需要 Python 3.13、PyTRIO 0.2.9；训练和推理通过 PyTRIO 托管服务执行。项目密钥从上层 `laya/.env` 读取，SwanLab 关闭。

```bash
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -r requirements.txt
. .venv/bin/activate
ROOT="$(cd ../../../../../ && pwd)"
DATA_DIR="$ROOT/typesafe-docs-zh/main/10_本地模型/data_generation/generated/sharegpt_zh_38k/v2/pytrio-custom-v2-20260929"

python prepare_dataset.py \
  --candidates ../../data_generation/generated/sharegpt_zh_38k/v2/laya_candidates.jsonl \
  --output-dir ../../data_generation/generated/sharegpt_zh_38k/v2/pytrio-custom-v2-20260929

python "$ROOT/laya/experiments/pytrio-jev-20260928/run.py" train \
  --data "$DATA_DIR/train.jsonl" \
  --epochs 2 --batch-size 16 --learning-rate 1e-4 --lora-rank 32 \
  --save-every 60 --swanlab-mode disabled \
  --experiment-name pytrio-laya-v2-20260929 \
  --weights-name pytrio-laya-v2-20260929

python evaluate_custom.py \
  --test "$DATA_DIR/test.jsonl" \
  --calibration "$DATA_DIR/calibration.jsonl" \
  --output-dir outputs --tag lora-test \
  --weights trio://run_rc3f5qm749kc/sampler_weights/pytrio-laya-v2-20260929-step-150
```

若要评估基础模型，省略 `--weights` 并使用不同的 `--tag`。脚本保存逐字段预测概率、硬标签准确率、软目标 CE/Brier、ECE 和按字段拆分的指标；不把原始对话正文写入评估结果。

## 方法对照

| 方案 | 基座与架构 | 训练目标 | 本地旧 test 结果 |
|---|---|---|---:|
| Laya Head-only | 321.9M multilingual encoder + 决策头 | 5 类决策头软标签 SFT，encoder 冻结 | accuracy 74.0%，soft CE 0.863 |
| Laya LoRA-SFT | 同上，attention LoRA + 决策头 | 软标签交叉熵 | accuracy 82.4%，soft CE 0.939 |
| Laya RLCD-style | 同上，全量 encoder + 决策头 | policy-gradient / proper-score 与低权重软 CE | accuracy 82.6%，soft CE 1.945 |
| PyTRIO LoRA-SFT（本实验） | Qwen3.5-4B causal LM，候选答案符号约束 | 每字段一个 token 的多数票硬标签 masked CE | 90.65%，soft CE 0.259；与前三者同 test |

当前 PyTRIO LoRA-SFT test accuracy 为 90.65%，相对 base 提升 16.30 个百分点；软交叉熵为 0.259。实验详见 [`RESULTS.md`](RESULTS.md)，其中包含分字段结果、模型架构差异和数据限制。Laya 的 soft CE 直接对照较有意义；架构大小、模型类型和训练目标不同，参数效率或因果效果不能只凭这次小实验归因。

## 产物

- `prepare_dataset.py`：数据校验与转换；不会改写 112 pilot。
- `evaluate_custom.py`：同一模型上一次采集 log-prob 后离线计算 raw / temperature-scaled 指标。
- `outputs/`：模型指标 JSON 与训练日志；权重由 PyTRIO 托管服务保存，地址写在本实验报告中。
- `outputs/<thread-id>/`：最终比较工作簿及可视化图。
