# 本地模型与 TypeSafe SDK

从上到下运行：确定模型 → 硬件评估 Prompt → GPU/CPU 选择 → 自动补齐模型 → 启动服务 → 发布连接配置 → 实测。
默认使用较小的多语言 Laya。服务只监听本机，不需要远程推理 API key；首次下载需要联网，文件完整后直接复用。
本次最小验收只覆盖 Windows 上的默认多语言 Laya；其他 Laya 权重、macOS/Linux、D1/LFM 和 LLaMA 暂未完成本次验证，已有实验入口保留。
首次克隆后先按 [README](../README.md#运行-notebook) 初始化项目环境，再用该环境的 Jupyter 打开本文件并执行 **Run All Cells**。默认模型依赖由初始化脚本一次装齐。
新环境的模型按仓库 ID 分目录保存在 `main/.models/`，可用 `JEV_MODEL_CACHE` 指定其他位置；已有本机连接配置时优先复用对应模型目录。其他 Notebook 用 HTTP 共享模型，避免重复加载。
当前交付只提供 Laya 服务；D1／LFM／LLaMA 暂只保留硬件参考，不随本分支提供适配服务。保留本 Notebook 内核和服务运行，再执行第 1～5 章现有 Notebook。

## 1. 导入与路径

只导入工具，不下载、不加载模型。请在本仓库内运行，保留与 LocalJev 同目录的辅助文件。
Windows 默认 Laya 环境由 `main/setup_env.ps1` 准备；已建立的环境也可用其 Python 安装本目录的 `requirements-local.txt`。不要在其他 Python 中安装后期待当前内核生效。其他平台不在本次初始化与验证范围内。

```python
import os
import sys
import json
from pathlib import Path

candidates = [Path.cwd(), *Path.cwd().parents]
MAIN_DIR = next((folder for root in candidates for folder in (root, root / "main")
                 if (folder / "LocalJev" / "local_jev_runtime.py").is_file()), None)
if MAIN_DIR is None:
    raise RuntimeError("请在 jevbook 仓库内运行，保留 LocalJev 配套辅助文件。")
LOCAL_DIR = MAIN_DIR / "LocalJev"
if str(LOCAL_DIR) not in sys.path:
    sys.path.insert(0, str(LOCAL_DIR))
from local_jev_runtime import (
    model_spec, model_paths, check_dependencies, hardware_report, ensure_model,
    start_service, wait_service, publish_connection, stop_service,
)
```

## 2. 确定模型

`MODEL_ID` 当前选择下表中的 Laya 模型；其他模型仅供硬件评估，适配服务暂不随本分支提交。目录名由完整 ID 生成，避免同名模型互相覆盖。
本地客户端的 `model` 字段由连接配置填入，不再固定为 Jev 模型名。Laya 服务使用 `local-laya-multilingual` 等合法别名，D1／通用适配使用仓库 ID。

```python
MODEL_ID = "convaiinnovations/laya-multilingual"
CACHE_DIR, MODEL_DIR = model_paths(MODEL_ID, MAIN_DIR)
PORT = 8001  # 如被其他服务占用，可改用空闲端口。
BASE_URL = f"http://127.0.0.1:{PORT}"
CONFIG_PATH = MAIN_DIR / ".local-jev.json"
LOG_PATH = CACHE_DIR / "local-jev-server.log"
SPEC = model_spec(MODEL_ID)
os.environ.setdefault("HF_ENDPOINT", "https://huggingface.co")
print("模型：", MODEL_ID, "｜后端：", SPEC["backend"])
print("模型目录：", MODEL_DIR)
```

## 3. 硬件评估 Prompt 区

紧接“确定模型”，单独一格。不调用模型或付费接口：填 `PROMPT_MODEL`，运行后复制打印的 Prompt 给 AI。
`{model}` 是模型占位符，`{hardware}` 会自动填入本机实际配置。也可填表外 ID，只评估、不下载。
分析结果不是实际启动验证。

```python
PROMPT_MODEL = MODEL_ID  # 也可填 "LiquidAI/d1-omni-600M" 或其他待评估模型
HARDWARE = hardware_report()
PROMPT_TEMPLATE = """请评估模型 {model} 能否在以下电脑上做本地推理。
实际硬件与 Python/PyTorch 配置：
{hardware}
用途：接入 TypeSafe SDK，处理中文文本／JSON 的 Choice、Score、Noul，单请求、短上下文。
核对官方模型卡及当前版本，区分原生决策与通用语言模型，不假设所有模型自带 system_one。
分别估算 FP32 CPU、FP16/BF16 GPU 的权重、加载峰值、运行开销与上下文用量。
若建议量化，区分本 Notebook 已实现的加载方式与需要额外实现的方案。
同时检查总内存和当前空闲内存／显存；MoE 按总参数计算驻留权重。
核实当前 PyTorch 是否可用 CUDA，不只看是否装有显卡；列出必要依赖版本。
指出是否需要接受权重许可或 HF 下载凭据；本地推理不应需要远程 API key。
输出：能否运行、推荐设备、精度、合理上下文、资源余量、瓶颈、具体准备步骤。
未知信息列为待验证，不把硬件估算写成实测结论。"""
HARDWARE_PROMPT = PROMPT_TEMPLATE.format(
    model=PROMPT_MODEL, hardware=json.dumps(HARDWARE, ensure_ascii=False, indent=2))
print(HARDWARE_PROMPT)
```

### 可选模型与硬件参考

资料核对日期：2026-10-11。下表是**推理估算**，不是厂商最低要求或本机实测：GPU 按未量化 FP16/BF16，CPU 按 FP32，短文本、单请求估算。
RAM／显存列都是运行时建议**空闲量**，系统与其他程序另需空间。权重只是下限，加载峰值、激活、上下文和框架开销会增加用量。

| MODEL_ID | 后端类型（非 Laya 仅供参考） | CPU 建议可用 RAM | GPU 建议空闲显存 | 说明 |
|---|---|---:|---:|---|
| `convaiinnovations/laya-multilingual` | 原生 Laya，默认 | 4 GiB | 2 GiB | 小型多语言决策模型；中文教程优先选它 |
| `convaiinnovations/laya` | 原生 Laya | 4 GiB | 2 GiB | 英文决策模型，中文效果需验证 |
| `LiquidAI/d1-omni-600M` | 原生 D1 | 6 GiB | 3 GiB | 约 587M 参数；transformers ≥5.15；本服务只接文本／JSON |
| `LiquidAI/d1-3B` | 原生 D1 | 16 GiB | 10 GiB | 较大决策模型；transformers ≥5.14；CPU 可尝试但更慢 |
| `LiquidAI/LFM2.5-350M` | 通用模型实验适配 | 4 GiB | 2 GiB | 小型通用模型；新版依赖；不是 D1 |
| `LiquidAI/LFM2.5-2.6B` | 通用模型实验适配 | 14 GiB | 8 GiB | transformers ≥5.0；8GB 显卡余量较紧 |
| `meta-llama/Llama-3.2-1B-Instruct` | 通用模型实验适配 | 8 GiB | 4 GiB | LLaMA 小模型；下载通常要先接受许可并配置 HF_TOKEN |
| `meta-llama/Llama-3.2-3B-Instruct` | 通用模型实验适配 | 16 GiB | 10 GiB | 3B 模型，优先足够显存的 GPU |
| `meta-llama/Llama-3.1-8B-Instruct` | 通用模型实验适配 | 40 GiB | 24 GiB | 较大模型；本流程不自动量化或卸载 |

本次只在实际服务中验证了默认多语言 Laya；英文 Laya 尚未完成端到端验证，D1／LFM／LLaMA 的适配服务暂不提交，表内依赖和硬件估算只供后续参考。

LLaMA／LFM 适配读取选项字母的 logits 并归一化，映射到 Choice／Score／Noul；`confidence` 是归一化熵的分布统计，**不是校准正确率，也不等同于 Jev／D1 的数值**。可运行 SDK 结构和控制流实验，不能直接套用教程原有模型结论。最多 26 个选项、4096 tokens；超出会报错，不静默截断。

更大模型如 Llama 70B：FP16 权重约 140 GB，尚未计入运行开销，通常需要多卡；4-bit 权重下限约 35 GB，但本流程未实现量化。MoE 内存按**总参数**而不是每次激活参数估算。表外 ID 在下载前明确报错，可先在上面 Prompt 区评估。

来源：[Laya Multilingual](https://huggingface.co/convaiinnovations/laya-multilingual)、[Open D1](https://www.liquid.ai/blog/d1-open)、[D1 600M](https://huggingface.co/LiquidAI/d1-omni-600M)、[D1 3B](https://huggingface.co/LiquidAI/d1-3B)、[LFM2.5 350M](https://huggingface.co/LiquidAI/LFM2.5-350M)、[LFM2.5 2.6B](https://huggingface.co/LiquidAI/LFM2.5-2.6B)、[Llama 1B](https://huggingface.co/meta-llama/Llama-3.2-1B-Instruct)、[Llama 8B](https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct)。

## 4. 检查依赖

检查所选模型需要的包及最低版本，不自动升级当前内核。缺包按提示安装后重启。
D1 自定义实现通过 `trust_remote_code=True` 从已下载的官方仓库文件加载；建议新版 D1／LFM 使用独立内核。

```python
check_dependencies(MODEL_ID)
print("依赖齐全。当前 Python：", sys.executable)
```

## 5. 选择设备

优先当前 PyTorch 可用的 NVIDIA CUDA GPU，其次 Apple MPS，最后 CPU。有显卡但 PyTorch 是 CPU 版会明确提示。
显存不够时不偷偷切 CPU：先释放显存、改小模型，或手动把 DEVICE 设成 `cpu`。
要启用 NVIDIA GPU，按 [PyTorch 官方安装选择器](https://pytorch.org/get-started/locally/) 选择与系统、驱动、内核匹配的版本。

```python
DEVICE = HARDWARE["device"]
print(json.dumps(HARDWARE, ensure_ascii=False, indent=2))
print("本次设备：", DEVICE)
available = HARDWARE.get("vram_free_gib") if DEVICE == "cuda" else HARDWARE["ram_available_gib"]
recommended = SPEC["vram_gib"] if DEVICE == "cuda" else SPEC["ram_gib"]
if available is not None and available < recommended:
    print(f"当前空闲资源约 {available} GiB，低于参考 {recommended} GiB；建议先释放资源或选小模型。")
```

## 6. 自动检查并准备模型

检查配置、tokenizer、权重和 D1 自定义代码，识别截断权重，不加载模型。完整时跳过下载，可离线运行；缺失时自动补齐并复检。
下载中断后重跑会复用缓存，损坏文件会重新拉取。公开模型无需 HF_TOKEN；LLaMA 的 HF_TOKEN 仅用于授权下载。

```python
downloaded_model_path = ensure_model(MODEL_ID, MODEL_DIR)
```

## 7. 启动本地服务

用当前内核的 Python 在后台启动所选后端，服务只加载本地目录，关闭 Hugging Face／Transformers 在线访问。
重复运行可复用匹配的就绪服务；其他进程占用端口时明确报错。切换模型或设备前先停止原服务。

```python
laya_process, SERVICE_CONFIG = start_service(
    MODEL_ID, MODEL_DIR, DEVICE, PORT, CONFIG_PATH, LOG_PATH,
    process=globals().get("laya_process"),
)
```

## 8. 等待服务就绪

最多等 180 秒，检查实际设备和驻留模型。进程退出或超时会报错；超时不会杀进程，可查日志后重跑本格。

```python
service_ready = False
HEALTH = wait_service(laya_process, SERVICE_CONFIG, timeout=180)
service_ready = True
print(json.dumps(HEALTH, ensure_ascii=False, indent=2))
```

## 9. 查看日志（可选）

```python
if LOG_PATH.exists():
    print(LOG_PATH.read_text(encoding="utf-8", errors="replace")[-5000:])
else:
    print("尚无日志。")
```

## 10. 发布连接配置

就绪后写 `.local-jev.json`，供其他独立内核读取；该文件已被 Git 忽略。
SDK 必须接收非空 key：服务自动生成本地随机凭据，不需要申请远程 key，不打印凭据。
第 1～4 章 25 本 SDK 教程已加自动读取格，第 5 章的智能家居 Notebook 会将同一连接交给其网页服务。在仓库内运行即可发现本地服务；检测到配置但服务不可用直接报错。
`JEV_RUN_MODE=offline` 仍可强制人工离线模式；本地模式使用 `live`，失败不退回人工答案。

```python
if not service_ready:
    raise RuntimeError("请先确认服务就绪。")
publish_connection(SERVICE_CONFIG, CONFIG_PATH)
import runpy
runpy.run_path(str(LOCAL_DIR / "use_local_jev.py"))
print("其他 Notebook 已可使用本地服务。连接配置：", CONFIG_PATH)
```

自建 Notebook 可在创建 SDK 客户端前执行：

```ipython
# 在 main 下运行；其他目录改成相对该 Notebook 的路径。
%run ./LocalJev/use_local_jev.py
```

之后用 `TypeSafeClient()`，或把自定义客户端的 `model` 改成 `os.environ["TYPESAFE_DEFAULT_MODEL"]`。`base_url` 用根地址，不加 `/v1`；已有客户端要重新创建。
第 5 章的 TypeSafe 判断可走本地模型；语音与生成式聊天仍有独立依赖或凭据。第 6 章及之后章节留待单独适配和验证。

## 11. 创建 SDK 客户端

```python
from typesafe_sdk import TypeSafeClient, Choice, Score, Noul, RetryPolicy
if "client" in globals():
    client.close()
client = TypeSafeClient(timeout=120.0, retry=RetryPolicy(max_retries=0))
print("客户端使用本地模型：", os.environ["TYPESAFE_DEFAULT_MODEL"])
```

## 12. 准备请求

同时核对三种原语。

```python
state = {"body": "我这个月被重复扣费了，请退回多扣的钱。"}
questions = {
    "department": Choice(instructions="这条消息应该交给哪个部门？",
                         criteria={"billing": "扣费、账单、退款", "technical": "软件故障、无法登录", "other": "其他问题"}),
    "refund": Noul(instructions="用户是否要求退款？"),
    "urgency": Score(instructions="这条消息有多紧急？", criteria=["可以稍后处理", "需要今天处理", "必须立即处理"]),
}
```

## 13. 发送预测请求

```python
response = client.system_one(state=state, questions=questions)
```

## 14. 查看真实结果

接口兼容不表示准确率、校准或速度与 Jev 相同，通用模型适配的概率语义尤其不同。

```python
print("实际模型：", response.model)
print("选择的部门：", response.choices["department"].choice)
print("退款概率：", response.nouls["refund"].noul)
print("紧急程度：", response.scores["urgency"].score)
print(response)
```

## 15. 停止服务

默认保留服务供其他 Notebook 使用。结束时改成 True，仅停止本内核持有的进程并移除它发布的配置。
重启内核前先停服务，避免丢失进程句柄。复用其他内核启动的服务时，本格不擅自结束它。
其他内核已创建的客户端仍持有旧配置；恢复远程配置请清理其 TYPESAFE 环境变量或重启内核。

```python
STOP_SERVICE = False
if STOP_SERVICE:
    if "client" in globals():
        client.close()
    if stop_service(laya_process, SERVICE_CONFIG, CONFIG_PATH):
        service_ready = False
        for name in ("TYPESAFE_API_KEY", "TYPESAFE_BASE_URL", "TYPESAFE_DEFAULT_MODEL", "JEV_RUN_MODE"):
            os.environ.pop(name, None)
else:
    print("服务保持运行；停止时把 STOP_SERVICE 改成 True。")
```
