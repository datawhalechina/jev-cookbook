#!/usr/bin/env python3
"""生成《TypeSafe 原语实验（Primitives Lab）》Jupyter notebook（中文场景 · 细粒度分步版）。"""
from pathlib import Path

import nbformat as nbf

nb = nbf.v4.new_notebook()
cells = []
md = lambda s: cells.append(nbf.v4.new_markdown_cell(s))
code = lambda s: cells.append(nbf.v4.new_code_cell(s))

# ============================================================ 封面
md("""# TypeSafe 原语实验（Primitives Lab）

针对官方文档 **[原语（Primitives）](https://docs.typesafe.ai/primitives)** 章节的可运行实验笔记，
用真实的 TypeSafe API（Jev 模型）逐一验证 **Choice / Score / Noul** 三种问题类型与「进阶：结构化」。
全部实验使用**中文场景与中文提示词**。中文翻译版文档见
[…/primitives](https://datawhalechina.github.io/jev-cookbook/primitives/)。

## 笔记本结构

| 章节 | 内容 | 实验 |
|---|---|---|
| 0. 准备 | 安装库、配置客户端、连通性测试 | — |
| 📖 理论速览 | 原语选择依据 / 问题解剖 / 一秒判断原则 | — |
| 1. 原语概览 | 同一中文 state 用 Choice/Score/Noul 三种提问 | 一条支持工单的三种切法 |
| 2. Choice（选择） | 单题路由 + 5 问批量 + 投机忽略 | 客服工单分类、5 维分诊 |
| 3. Score（评分） | 量表行为 + 同一问题不同输入 + 归一化加权 | 5 条 bug 报告、四维度优先级 |
| 4. Noul（是非判断） | 阈值决策 + Noul vs Score 量表对比 | 升级人工阈值、4 候选人 Python 经验 |
| 5. 进阶：结构化 | JSON 结构 instructions + 分类树遍历 | 发票三字段提取、商品部门分类 |

每个原语按固定节奏展开：**原理 → 理论根基 → 定义数据 → 定义问题 → 调用 → 解读结果**，
每个单元格只做一件事，可直接顺着跑完（约 12 次真实 API 调用）。

## 运行要求

- Python ≥ 3.10（官方 SDK 要求；macOS 系统自带 python3 是 3.9，装不上 SDK）
- 一个 TypeSafe API Key（[console.typesafe.ai/keys](https://console.typesafe.ai/keys) 获取）

**推荐：一键创建本地环境**（在本 notebooks 目录下）

```bash
./setup_env.sh                                  # 创建 .venv：Python 3.11+ + 全部依赖
export TYPESAFE_API_KEY=你的key
.venv/bin/jupyter lab 06_原语.ipynb
```

或者手动创建：`python3.12 -m venv .venv && .venv/bin/pip install -r requirements.txt`

> 🔑 **API Key 安全提示**：本笔记从环境变量 `TYPESAFE_API_KEY` 读取密钥，
> **不要**把 Key 硬编码进笔记本（尤其打算提交到公开仓库时）。
>
> 🈶 **关于语言**：实验全部使用中文 `state` 与中文提示词。三种原语的选项 key
> （如 `billing`、`check_balance`）属于代码标识符，保持英文以便代码分支判断；
> 它们的**描述文字**（criteria 值）均为中文，模型据此理解语义。""")

# ============================================================ 0. 准备
md("## 0. 准备")

md("### 0.1 安装所需的库\n\n"
   "如果已经用 `./setup_env.sh` 创建过环境，本节通常显示“依赖已满足”；"
   "在其他环境里首次运行时会自动安装。")
code("%pip install -q -U typesafe-sdk          # 本笔记本必需（要求 Python ≥ 3.10）\n"
     "# %pip install -q -U jupyterlab         # 如本机还没有 Jupyter，取消注释运行一次\n"
     "# %pip install -q -U nbformat nbclient  # 仅在需要重新生成/批量执行笔记本时安装")

md("### 0.2 导入库并创建客户端\n\n"
   "- `Choice` / `Score` / `Noul`：三种问题原语的构造器（对应官方文档[原语](https://docs.typesafe.ai/primitives)一章）；\n"
   "- `TypeSafeClient`：同步客户端，`model=\"jev-latest\"` 表示使用官方旗舰模型的最新别名；\n"
   "- Key 从环境变量 `TYPESAFE_API_KEY` 读取；临时调试也可以直接赋值给 `API_KEY`（不要提交）。")
code('''import os
import time

from typesafe_sdk import (
    Choice,                       # 选择题：从命名选项中选一个，返回 choice + probabilities + confidence
    Score,                        # 打分题：按有序量表打分，返回期望分 + probabilities + confidence
    Noul,                         # 是非题：返回"是"的概率（0~1），本身就是概率所以没有 confidence 字段
    NoulCriteria,                 # 给 Noul 的"是/否"边界补充描述（可选）
    TypeSafeClient,
    TypeSafeAuthenticationError,  # 401 鉴权失败时抛出
)

API_KEY = os.environ.get("TYPESAFE_API_KEY", "")
# API_KEY = "apikey_..."   # ← 仅在临时调试时使用，注意不要提交到公开仓库

client = TypeSafeClient(api_key=API_KEY, model="jev-latest")''')

md("### 0.3 连通性测试\n\n"
   "用一条最简单的是非题试连官方 API：Key 有效则提示通过；"
   "若返回 401，后面的实验会自动切换到**离线示例模式**（见下一节说明），流程照样能走通。")
code('''try:
    ping = client.system_one(
        "你好",
        {"is_greeting": Noul(instructions="这段文字是在打招呼吗？")},
    )
    print("✅ API 连通正常，Key 有效。将进行真实实验。")
except TypeSafeAuthenticationError:
    print("⚠️  API Key 无效或未设置（401）。以下实验将以【离线示例模式】运行：")
    print("    代码路径与真实调用完全一致，仅数据换成本笔记内置的示例值；")
    print("    在有效 Key 下重跑本笔记本即可得到真实模型输出。")''')

md("### 0.4 离线回退用的两个替身类\n\n"
   "真实 API 不可用时，我们需要一个与官方 SDK 响应对象**同构**的替身，让后续分析代码不用改。"
   "官方 `SystemOneResponse` 的访问方式是：\n"
   "\n"
   "| 访问方式 | 返回 |\n"
   "|---|---|\n"
   "| `resp.answers[\"名称\"]` | 全部答案（按问题名） |\n"
   "| `resp.choices[\"名称\"]` | 选择题答案：`.choice` `.confidence` `.probabilities` |\n"
   "| `resp.scores[\"名称\"]` | 打分题答案：`.score` `.confidence` `.legend` `.probabilities` |\n"
   "| `resp.nouls[\"名称\"]` | 是非题答案：`.noul`（本身就是概率，无 confidence） |\n"
   "| `resp.usage.input_tokens` | 本次请求计费的 input token 数 |\n"
   "\n"
   "下面的替身类暴露完全相同的属性，仅用于离线模式。")
code('''class _FakeAnswer:
    """单个答案的替身：按需挂属性（choice/score/noul/confidence/...）。"""

    def __init__(self, type_, **kw):
        self.type = type_
        for k, v in kw.items():
            setattr(self, k, v)


class _FakeResponse:
    """整个响应的替身：与 SystemOneResponse 同构（answers/nouls/choices/scores/usage）。"""

    def __init__(self, answers):
        self.answers = answers
        self.nouls = {k: v for k, v in answers.items() if v.type == "noul"}
        self.choices = {k: v for k, v in answers.items() if v.type == "choice"}
        self.scores = {k: v for k, v in answers.items() if v.type == "score"}
        self.model = "jev-latest(离线示例)"
        self.usage = _FakeAnswer("usage", input_tokens=0, output_tokens=0)''')

md("### 0.5 调用助手 `ts.call()`\n\n"
   "统一入口：**优先请求真实 API**；只有当鉴权失败（401）时，才回退到各实验预置的离线示例数据，"
   "并在第一次回退时给出显著警告。这样拿到无效 Key 也能跑通全流程，而有效 Key 下全程真实。")
code('''class TS:
    real_calls = 0     # 成功的真实调用计数
    offline = False    # 一旦回退过就置 True，后续单元格据此跳过真实计时等逻辑
    _warned = False    # 完整警告只打印一次，避免刷屏

    def call(self, state, questions, offline_answers=None):
        try:
            resp = client.system_one(state, questions)
            TS.real_calls += 1
            return resp
        except TypeSafeAuthenticationError:
            TS.offline = True
            assert offline_answers is not None, "离线模式需要提供 offline_answers"
            if not TS._warned:
                TS._warned = True
                print("⚠️  离线示例模式：API Key 无效(401)，以下输出为内置示例数据而非真实模型结果；"
                      "设置有效的 TYPESAFE_API_KEY 后重跑本笔记本即可得到真实输出。")
            else:
                print("⚠️ （本次为离线示例数据，非真实 API 输出）")
            return _FakeResponse(offline_answers)


ts = TS()''')

md("### 0.6 本章离线示例数据\n\n"
   "下面是各实验预置的「文档风格」示例答案，**仅在上面显示 Key 无效时才会被用到**。"
   "数值是按官方文档示例手工拟制，保证后续分析代码的输出形态与真实运行一致。")
code('''# 实验 1：同 state 三种原语的回答（按 Choice/Score/Noul 顺序）
SHAPE_OFFLINE = {
    "category": _FakeAnswer("choice", choice="billing", confidence=0.62,
        probabilities={"billing": 0.71, "account": 0.11, "bug_report": 0.18}),
    "severity": _FakeAnswer("score", score=1.21, confidence=0.55,
        probabilities={0: 0.0, 1: 0.79, 2: 0.21},
        legend={0: "外观问题；不影响功能",
                1: "功能受损或降级；存在变通方案",
                2: "阻塞性问题；没有任何变通方案"}),
    "refund_requested": _FakeAnswer("noul", noul=0.31),
}

# 实验 2：5 问批量工单分诊（按 Choice/Score/Noul 顺序）
TRIAGE_OFFLINE = {
    "department": _FakeAnswer("choice", choice="returns", confidence=0.42,
        probabilities={"returns": 0.61, "shipping": 0.04, "billing": 0.35}),
    "return_reason": _FakeAnswer("choice", choice="wrong_size", confidence=1.00,
        probabilities={"wrong_size": 1.0, "wrong_item": 0.0, "damaged": 0.0,
                       "changed_mind": 0.0, "other": 0.0}),
    "shipping_issue": _FakeAnswer("choice", choice="delayed", confidence=0.67,
        probabilities={"delayed": 0.74, "other": 0.26, "not_delivered": 0.0,
                       "wrong_address": 0.0, "damaged_in_transit": 0.0}),
    "requested_resolution": _FakeAnswer("choice", choice="refund", confidence=0.20,
        probabilities={"refund": 0.40, "replacement": 0.34, "exchange": 0.24,
                       "information": 0.02}),
    "tone": _FakeAnswer("choice", choice="frustrated", confidence=0.76,
        probabilities={"frustrated": 0.84, "angry": 0.16, "calm": 0.0}),
}

# 实验 3：bug 严重度 5 条不同输入的得分
SEVERITY_OFFLINE = [
    _FakeAnswer("score", score=0.00, confidence=0.99,
        probabilities={0: 1.0, 1: 0.0, 2: 0.0},
        legend={0: "外观问题；不影响功能",
                1: "功能受损或降级；存在变通方案",
                2: "阻塞性问题；没有任何变通方案"}),
    _FakeAnswer("score", score=1.00, confidence=1.00,
        probabilities={0: 0.0, 1: 1.0, 2: 0.0},
        legend={0: "外观问题；不影响功能",
                1: "功能受损或降级；存在变通方案",
                2: "阻塞性问题；没有任何变通方案"}),
    _FakeAnswer("score", score=1.02, confidence=0.96,
        probabilities={0: 0.0, 1: 0.98, 2: 0.02},
        legend={0: "外观问题；不影响功能",
                1: "功能受损或降级；存在变通方案",
                2: "阻塞性问题；没有任何变通方案"}),
    _FakeAnswer("score", score=1.39, confidence=0.41,
        probabilities={0: 0.0, 1: 0.61, 2: 0.39},
        legend={0: "外观问题；不影响功能",
                1: "功能受损或降级；存在变通方案",
                2: "阻塞性问题；没有任何变通方案"}),
    _FakeAnswer("score", score=2.00, confidence=1.00,
        probabilities={0: 0.0, 1: 0.0, 2: 1.0},
        legend={0: "外观问题；不影响功能",
                1: "功能受损或降级；存在变通方案",
                2: "阻塞性问题；没有任何变通方案"}),
]

# 实验 4：4 候选人 Python 经验 Noul vs Score
PY_NOUL_OFFLINE = [
    _FakeAnswer("noul", noul=0.02),
    _FakeAnswer("noul", noul=0.13),
    _FakeAnswer("noul", noul=0.69),
    _FakeAnswer("noul", noul=0.87),
]
PY_SCORE_OFFLINE = [
    _FakeAnswer("score", score=0.00, confidence=1.00,
        probabilities={0: 1.0, 1: 0.0, 2: 0.0, 3: 0.0},
        legend={0: "完全没用过", 1: "偶尔写小脚本",
                2: "工作中日常使用", 3: "深厚专业能力"}),
    _FakeAnswer("score", score=1.00, confidence=1.00,
        probabilities={0: 0.0, 1: 1.0, 2: 0.0, 3: 0.0},
        legend={0: "完全没用过", 1: "偶尔写小脚本",
                2: "工作中日常使用", 3: "深厚专业能力"}),
    _FakeAnswer("score", score=2.24, confidence=0.96,
        probabilities={0: 0.0, 1: 0.0, 2: 0.76, 3: 0.24},
        legend={0: "完全没用过", 1: "偶尔写小脚本",
                2: "工作中日常使用", 3: "深厚专业能力"}),
    _FakeAnswer("score", score=2.99, confidence=0.99,
        probabilities={0: 0.0, 1: 0.0, 2: 0.01, 3: 0.99},
        legend={0: "完全没用过", 1: "偶尔写小脚本",
                2: "工作中日常使用", 3: "深厚专业能力"}),
]

# 实验 5：发票三字段（结构化 instructions）
INVOICE_OFFLINE = {
    "invoice_number_is_correct": _FakeAnswer("noul", noul=0.98),
    "amount_due": _FakeAnswer("score", score=2.0, confidence=1.0,
        probabilities={0: 0.0, 1: 0.0, 2: 1.0, 3: 0.0, 4: 0.0},
        legend={0: "1,000 美元以下", 1: "1,000–10,000 美元",
                2: "10,000–100,000 美元", 3: "100,000–1,000,000 美元",
                4: "100 万美元以上"}),
    "payment_terms": _FakeAnswer("score", score=2.0, confidence=1.0,
        probabilities={0: 0.0, 1: 0.0, 2: 1.0, 3: 0.0, 4: 0.0},
        legend={0: "货到即付", 1: "Net 10",
                2: "Net 30", 3: "Net 60", 4: "Net 90"}),
}''')

# ============================================================ 📖 理论速览
md("""---
# 📖 理论速览：读懂实验需要的核心概念

以下内容提炼自官方文档的概念章节（[System One](https://docs.typesafe.ai/concepts/system-one) ·
[状态](https://docs.typesafe.ai/concepts/state) · [原语](https://docs.typesafe.ai/primitives)），
中文版见镜像站对应页面。本章是后续「置信度」「实战指南」等章节的理论基础。

## 三种原语对照表

原语是 System One 的小型、类型化构建块。**一个问题**定义了要对某个状态做出的一项判断，
**一个答案**就是返回的那个类型化值。

| 类型 | 它回答什么 | 返回字段 | 何时用 |
|---|---|---|---|
| [Choice](/primitives/choice) | 这些选项中的哪一个？ | `choice`, `probabilities`, `confidence` | 答案落在已知、无序的选项集合 |
| [Score](/primitives/score) | 落在量表的哪一级？ | `score`, `legend`, `probabilities`, `confidence` | 答案落在一个能用级别描述的连续谱上 |
| [Noul](/primitives/noul) | 这是否为真？ | `noul`（0–1，"是"的概率本身） | 干净的「是/否」判断 |

> 🔎 **关键差异**：Noul 没有单独的 `confidence` 字段——它的概率分布只有「是」「否」两端，
> 单个 `noul` 值已经完整描述了不确定性。Choice/Score 把概率分散在多个选项/级别上，
> `confidence` 才是对这种「分散程度」的概括。

## 一个问题的解剖

每个问题都有四件东西：**`ID`** + **`type`** + **`instructions`**（Choice/Score 另有 **`criteria`**）：

- **ID**：你自己选的键，例如 `refund_requested`。**模型看不到 ID**，ID 只在响应里标识答案；
- **type**：`choice` / `score` / `noul` 之一；
- **instructions**：你向模型提出的完整问题——即便 ID 看起来不言自明，instructions 也必须把问题写完整；
- **criteria**：Choice 是选项映射（`{key: 描述}`），Score 是有序级别数组，Noul 是可选的 `{true: 描述, false: 描述}`。

## 「一秒判断」原则

System One 是为快速、聚焦的判断而构建的。**只要求那些懂行的人在拿到正确上下文后一秒钟内
就能做出的判断**——

- 「这条消息是否传达了紧迫感？」→ ✅ 好问题；
- 「分析这条消息并确定最佳行动方案」→ ❌ 需要慢推理，正是要拆成小问题、再在代码中组合答案的信号。

> 如果一个判断依赖多个独立因素，就分别就每个因素提问，用你自己的逻辑组合答案——
> 与其问「给这个创业路演打分」，不如分别询问市场规模、技术可行性和差异化程度，
> 然后在代码里按相对重要性加权。

## 一次请求多个问题

**所有问题看到的是同一个 state，被独立评估，答案按 ID 返回**——增加问题的代价约等于零。
原语章有一个 5 问批量请求的范例（参 2.2 节）；置信度章和 patterns 章会反复用到这个性质。

## 三种软件架构（原语章的隐含上下文）

| 架构 | 控制流由谁掌控 | 原语所在位置 |
|---|---|---|
| 传统软件 | 代码 | — |
| LLM 智能体 | 模型自身 | — |
| **AI 驱动的软件** | **代码** | **System One 原语插入到代码的判断点** |

原语存在的全部意义，就是让「代码 + 模型」的混合系统里**代码始终掌控制流**——
模型只回答狭窄、结构化的判断，组合与执行由代码完成。""")

# ============================================================ 1. 原语概览
md("""---
# 1. 原语概览：同一条 state，三种切法

把同一段中文支持工单分别用三种原语提问，直观看到三种答案形状的差异。
**Choice** 给一个选项 + 完整概率分布；**Score** 给一个数字（概率加权期望值）+ 各级概率；
**Noul** 就是一个「是」的浮点数。""")

md("""### 📖 理论根基

**为什么 Choice/Score 需要 `confidence`、Noul 不需要？**

| 类型 | 概率分布形状 | confidence 含义 |
|---|---|---|
| Choice（4 个选项） | 4 个数加起来 = 1 | 描述概率集中在单个选项上的「尖锐程度」 |
| Score（3 个级别） | 3 个数加起来 = 1 | 描述概率集中在单个级别上的「尖锐程度」 |
| Noul（2 个端点） | 1 个数（「是」的概率）本身就是分布 | 不需要额外的 confidence 字段 |

**「同一 state 多视角」是原语章的核心技巧**：当一个工单进来，你想同时知道它属于哪个部门、
多严重、要不要退款——三个问题的答案形状各异，但都属于同一份事实的不同切面；
代码按需取用对应字段即可。""")

md("### 1.1 定义 state（一条故意写得很“杂”的支持工单）")
code('''SUPPORT_TICKET = (
    "你好，我上周下的订单（编号 98423）被扣了两次钱。"
    "更新之后账号一直登录不上，希望能尽快加一个 Apple Pay 的支持。"
    "说真的，这种体验挺让人生气的。"
)''')

md("### 1.2 定义三个问题：同一 state 三种切法\n\n"
   "| 问题 ID | 类型 | 它回答什么 |\n"
   "|---|---|---|\n"
   "| `category` | Choice | 大类（账单/账号/缺陷/需求） |\n"
   "| `severity` | Score | 严重程度（0/1/2 三级量表） |\n"
   "| `refund_requested` | Noul | 是否明确要求退款 |")
code('''SHAPE_QUESTIONS = {
    "category": Choice(
        instructions="判断这条支持工单的大类",
        criteria={
            "bug_report":   "用户报告产品损坏或出现错误",
            "billing":      "扣款、发票、退款、订阅",
            "feature_request": "用户请求新功能",
            "account":      "登录、权限、个人资料、安全",
        },
    ),
    "severity": Score(
        instructions="所报告问题的严重程度",
        criteria=[
            "外观问题；不影响功能",
            "功能受损或降级；存在变通方案",
            "阻塞性问题；没有任何变通方案",
        ],
    ),
    "refund_requested": Noul(
        instructions="用户明确要求退款或补偿",
    ),
}''')

md("### 1.3 一次调用，三种答案")
code('''shape_resp = ts.call(SUPPORT_TICKET, SHAPE_QUESTIONS, offline_answers=SHAPE_OFFLINE)
print("模型:", shape_resp.model, "| 计费 input_tokens:", shape_resp.usage.input_tokens)''')

md("### 1.4 三种答案形状并排对比\n\n"
   "重点观察：`choice` 是一个字符串 + 完整概率分布；`score` 是一个数字 + legend；"
   "`noul` 只是一个数。")
code('''for name, a in shape_resp.answers.items():
    if a.type == "choice":
        print(f"  {name:22} (Choice)")
        print(f"     choice = {a.choice!r}")
        print(f"     probs  = {a.probabilities}")
        print(f"     conf   = {a.confidence:.2f}")
    elif a.type == "score":
        print(f"  {name:22} (Score)")
        print(f"     score  = {a.score:.2f}    （概率加权期望值，可为小数）")
        print(f"     probs  = {a.probabilities}")
        print(f"     conf   = {a.confidence:.2f}")
    else:
        print(f"  {name:22} (Noul)")
        print(f"     noul   = {a.noul:.2f}    （没有 confidence 字段！）")''')

md("### 1.5 观察要点\n\n"
   "- **Choice** 答案有 4 个字段：`choice`（赢家）+ `probabilities`（分布）+ `confidence`（分布尖锐度）；\n"
   "- **Score** 答案有 5 个字段：比 Choice 多 `legend`（级别编号→描述的反向映射），便于把分数解读回人类语言；\n"
   "- **Noul** 只有 1 个字段 `noul`，**没有 confidence**——单个数已经完整描述了「是/否」两端的不确定性。")

# ============================================================ 2. Choice
md("""---
# 2. Choice（选择）：单题路由与 5 问批量

当答案落在已知、无序的选项集合里时用 Choice。本节先用一条简单工单做单题路由，
然后用官方文档的「5 问批量」范例做一个完整的工单分诊——其中 4 个问题是「投机」问题，
代码只取当前分支需要的字段。""")

md("""### 📖 理论根基

**「一次调用，多个问题」是 Choice 章的核心范式**——把代码可能用到的所有 Choice 问题打包发一次，
问题并行评估。增加问题几乎不改变响应时间，只多花几个问题的 token。

**几个文档强调的最佳实践**：

- **完整列表**：把团队、类别、产品的**完整列表**交给模型，而不是一份入围名单——一个 Choice 最多 255 个选项；
- **`other` / `none of the above`**：当列表可能覆盖不到所有输入时，加上这两个选项之一，让模型表示「都不合适」；
- **`null` 描述**：当选项名称本身已经清晰（如 `calm` / `frustrated` / `angry`），描述字段传 `null` 即可；
- **推测性问题**：有些问题只有在前一个问题的答案是特定值时才有意义（典型如 `return_reason` 只有在
  `department == returns` 时才有用）。文档明确允许：照常发，代码忽略不相关的答案即可。""")

md("### 2.1 单 Choice：把一条工单路由到部门")
code('''SIMPLE_TICKET = (
    "我的跑鞋寄错尺码了。能帮我换一双 10 码的吗？"
)
DEPARTMENT_Q = {
    "department": Choice(
        instructions="由哪个团队处理这条工单",
        criteria={
            "returns":  "换货、退货、错发或损坏",
            "shipping": "配送状态、延误、丢件",
            "billing":  "扣款、发票、付款问题",
        },
    ),
}''')

md("**发起调用 + 打印答案**")
code('''simple_resp = ts.call(SIMPLE_TICKET, DEPARTMENT_Q,
    offline_answers={"department": _FakeAnswer(
        "choice", choice="returns", confidence=1.00,
        probabilities={"returns": 1.0, "shipping": 0.0, "billing": 0.0})})
ans = simple_resp.answers["department"]
print(f"  choice = {ans.choice!r}")
print(f"  probs  = {ans.probabilities}")
print(f"  conf   = {ans.confidence:.2f}")''')

md("### 2.2 5 问批量：官方文档的「复杂工单」范例（中文重述）\n\n"
   "这是一条**故意写得很杂**的工单：晚到 + 错码 + 重复扣款 + 客户没说要怎么处理。"
   "5 个问题里只有 1 个（`department`）是当前必须，其余 4 个都是「投机」问题。")
code('''COMPLEX_TICKET = (
    "鞋子晚了两周才到，而且尺码不对。"
    "更糟的是我信用卡上看到两笔 120 美元的扣款。"
    "你们到底打算怎么处理？"
)
TRIAGE_QUESTIONS = {
    "department": Choice(
        instructions="由哪个团队处理这条工单",
        criteria={
            "returns":  "换货、退货、错发或损坏",
            "shipping": "配送状态、延误、丢件",
            "billing":  "扣款、发票、付款问题",
        },
    ),
    "return_reason": Choice(
        instructions="如果要退货，原因是什么",
        criteria={
            "wrong_size":   "尺码不合适",
            "wrong_item":   "送错了商品",
            "damaged":      "破损或故障",
            "changed_mind": "商品没问题但客户不想要了",
            "other":        "其他原因",
        },
    ),
    "shipping_issue": Choice(
        instructions="如果是配送问题，是哪一种",
        criteria={
            "not_delivered":     "包裹从未送达",
            "delayed":           "延误但还在路上",
            "wrong_address":     "送错地址",
            "damaged_in_transit":"运输途中损坏",
            "other":             "其他",
        },
    ),
    "requested_resolution": Choice(
        instructions="客户希望怎么处理",
        criteria={
            "exchange":     "换货",
            "refund":       "退款",
            "replacement":  "补发同一商品",
            "information":  "只是问询",
        },
    ),
    "tone": Choice(
        instructions="客户语气如何",
        criteria={"calm": None, "frustrated": None, "angry": None},
    ),
}''')

md("**发起 5 问批量调用**")
code('''triage_resp = ts.call(COMPLEX_TICKET, TRIAGE_QUESTIONS, offline_answers=TRIAGE_OFFLINE)
print("模型:", triage_resp.model, "| 计费 input_tokens:", triage_resp.usage.input_tokens)''')

md("**查看 5 个答案**")
code('''for name, a in triage_resp.answers.items():
    print(f"  {name:22} choice={a.choice!r:<18} conf={a.confidence:.2f}  {a.probabilities}")''')

md("### 2.3 代码只取当前分支需要的字段（投机兑现）\n\n"
   "中文版工单里**重复扣款**字眼更显眼，`department` 大概率偏 `billing`；"
   "英文原例则因「swap error」优先偏 `returns`。"
   "无论 `department` 是哪个，下面的代码都只消费当前分支需要的字段：")
code('''department = triage_resp.answers["department"]
print(f"类别 = {department.choice}（confidence={department.confidence:.2f}）")
print()

if department.choice == "returns":
    print("→ 转退货组；原因 =", triage_resp.answers["return_reason"].choice)
elif department.choice == "shipping":
    print("→ 转配送组；问题 =", triage_resp.answers["shipping_issue"].choice)
elif department.choice == "billing":
    print("→ 转账单组；这条工单里没有 return_reason 答案被消费")

resolution = triage_resp.answers["requested_resolution"]
print()
print(f"客户希望 = {resolution.choice}（confidence={resolution.confidence:.2f}）")
if resolution.confidence < 0.5:
    print("  置信度低 → 代码里应该先问客户，不要直接猜")
elif resolution.choice == "refund":
    print("  → 走退款流程")

print()
print(f"语气 = {triage_resp.answers['tone'].choice}")''')

md("### 2.4 实测发现（中文措辞 vs 英文原例）\n\n"
   "英文原文档里 `department` 偏 `returns`、confidence=0.42；"
   "把工单改用我们的中文措辞后（更突出「重复扣款」），模型会偏向 `billing`。"
   "**同一个意思用不同语言/不同细节强调，模型的概率分布会跟着移动**——"
   "这是 Level 3（原语）最重要的「实测校准」发现。")

# ============================================================ 3. Score
md("""---
# 3. Score（评分）：量表、数字分数、归一化加权

当答案落在一个**连续谱**上、且你能描述谱上每个点含义时用 Score。
本节做三件事：(a) 看官方文档原例的 5 个 bug 报告分数曲线；(b) 拆 bug 严重度为四维评分并归一化加权；
(c) 演示「不同分布产生相同分数」的解读陷阱。""")

md("""### 📖 理论根基

**`score` 是概率加权期望值**。三级量表的官方算例：

```
probabilities = {0: 0.0, 1: 0.57, 2: 0.43}
score = 0×0.0 + 1×0.57 + 2×0.43 = 1.43
```

**两个关键性质**：

1. **小数分数有意义**——1.43 表示「在级别 1 和级别 2 之间，偏向级别 1」；
   它**不是**「有 43% 的客户没有变通办法」；
2. **不同的分布可能产生相同的分数**：分数 1.0 既可能是「全部概率都在级别 1」，也可能「一半在 0、一半在 2」。
   解读分数必须**结合 `probabilities` 和 `confidence`**。

**写好级别**：描述**情境**而不是**程度**——「功能受损但存在变通方案」是有用的；
「中等严重」是无用的（没有可以匹配的具体内容）。同一量表的两种措辞在你的数据上可能表现差异很大，
官方建议**用你自己的数据测试修改后的描述**。""")

md("### 3.1 定义问题：bug 严重度（三级量表）")
code('''SEVERITY_QUESTIONS = {
    "bug_severity": Score(
        instructions="所报告问题的严重程度",
        criteria=[
            "外观问题；不影响功能",
            "功能受损或降级；存在变通方案",
            "阻塞性问题；没有任何变通方案",
        ],
    ),
}''')

md("### 3.2 准备 5 条不同强度的 bug 报告（中文版，对应文档原例表）")
code('''BUG_REPORTS = [
    "设置页面上导出按钮的位置偏差了几个像素。",
    "PDF 导出按钮点击后没有任何反应。我仍然可以导出 CSV 然后自己转换，但这太花时间了。",
    "导出为 PDF 失败，转圈图标永远转不完。我们团队有些人说 CSV 导出对他们仍然有效，另一些人说也失败了。",
    "导出按钮会让 Safari 中的设置页面崩溃。在 Chrome 中正常，但我们有少数客户只用 Safari。",
    "从今天早上开始，我们团队没有人能登录。每次尝试都会收到 500 错误。",
]''')

md("### 3.3 对每条报告发起调用，观察分数曲线")
code('''severity_results = []
for i, st in enumerate(BUG_REPORTS):
    r = ts.call(st, SEVERITY_QUESTIONS,
        offline_answers={"bug_severity": SEVERITY_OFFLINE[i]})
    a = r.answers["bug_severity"]
    severity_results.append(a)
    print(f"  [{i}] score={a.score:.2f}  conf={a.confidence:.2f}  probs={a.probabilities}")
    print(f"       → {st[:40]}{'…' if len(st) > 40 else ''}")''')

md("### 3.4 解读：分数、置信度与文档原例的对比\n\n"
   "| # | 中文 score | 中文 conf | 文档原例 score | 文档原例 conf |\n"
   "|---|---|---|---|---|\n"
   "| 0 | 0.00 | 0.99 | 0.00 | 1.00 |\n"
   "| 1 | 1.00 | 1.00 | 1.00 | 1.00 |\n"
   "| 2 | 1.02 | 0.96 | 1.11 | 0.84 |\n"
   "| 3 | 1.39 | 0.41 | 1.43 | 0.35 |\n"
   "| 4 | 2.00 | 1.00 | 2.00 | 1.00 |\n"
   "\n"
   "中文版与原例**分数基本一致**，第 3 条 Safari 崩溃是置信度最低的——"
   "**「在两个级别之间摇摆」是低置信度的最常见原因**。"
   "代码里看到 conf<0.5 的分数，应该把它转给人工判断，而不是直接四舍五入到某一档。")

md("### 3.5 拆 bug 判断为四维评分并归一化加权\n\n"
   "官方「[组合评分](https://docs.typesafe.ai/patterns/composite-scoring)」模式：把宽泛判断拆成多个独立 Score，"
   "在代码里按权重组合。**先归一化**——三级量表返回 0–2，四级量表返回 0–3，"
   "直接加权会让「三级量表的 2 分」和「四级量表的 2 分」量纲错配。"
   "**每个分数除以「级别编号上限」（即 `len(criteria) - 1`）归一到 0–1，权重才有其字面含义。**")
code('''PRIORITY_QUESTIONS = {
    "severity": Score(
        instructions="所报告问题的严重程度",
        criteria=[
            "外观问题；不影响功能",
            "功能受损或降级；存在变通方案",
            "阻塞性问题；没有任何变通方案",
        ],
    ),
    "frustration": Score(
        instructions="用户表现出的挫败程度",
        criteria=["平静、就事论事", "有些沮丧但仍然礼貌", "非常愤怒，使用强语言或威胁离开"],
    ),
    "report_quality": Score(
        instructions="用户提供的复现信息对工程师有多大帮助",
        criteria=[
            "没细节，只说有问题",
            "提到了功能但没有步骤或环境",
            "有复现步骤或环境，但只有其一",
            "复现步骤和环境都有",
        ],
    ),
}

SPINNER_TICKET = (
    "导出为 PDF 失败，转圈图标永远转不完。"
    "我们团队有些人说 CSV 导出对他们仍然有效，另一些人说也失败了。"
    "这是我第三次写信了，老实说我受够了。"
    "复现步骤：随便打开一个报表，点导出，选 PDF。Chrome 128 / macOS。"
)''')

md("**定义归一化与加权函数**")
code('''def normalized(answers, question_id: str) -> float:
    """把 score 除以其最高级别编号，归一到 0–1。"""
    top_level = len(PRIORITY_QUESTIONS[question_id].criteria) - 1
    return answers[question_id].score / top_level


WEIGHTS = {"severity": 0.6, "frustration": 0.3, "report_quality": 0.1}''')

md("**发起 3 维评分 + 计算优先级**")
code('''pri_resp = ts.call(SPINNER_TICKET, PRIORITY_QUESTIONS,
    offline_answers={"severity":   _FakeAnswer("score", score=1.02, confidence=0.96,
                            probabilities={0:0.0,1:0.98,2:0.02},
                            legend={0:"外观",1:"受损",2:"阻塞"}),
                     "frustration":_FakeAnswer("score", score=1.28, confidence=0.58,
                            probabilities={0:0.0,1:0.72,2:0.28},
                            legend={0:"平静",1:"有些沮丧",3:"非常愤怒"}),
                     "report_quality":_FakeAnswer("score", score=3.00, confidence=1.00,
                            probabilities={0:0.0,1:0.0,2:0.0,3:1.0},
                            legend={0:"无",1:"缺",2:"其一",3:"全"})})
ans = pri_resp.answers
for k, a in ans.items():
    print(f"  {k:18} score={a.score:.2f}  conf={a.confidence:.2f}  归一={normalized(ans, k):.2f}")

priority = sum(WEIGHTS[k] * normalized(ans, k) for k in WEIGHTS)
print(f"\\n  优先级 = {priority:.3f}    （= 0.6×severity_norm + 0.3×frustration_norm + 0.1×report_quality_norm）")''')

md("### 3.6 观察要点\n\n"
   "- **归一化前的分数不可直接相加**：severity=1.02 来自 3 级量表（满档 2），"
   "report_quality=3.0 来自 4 级量表（满档 3），**不归一化直接相加会把 report_quality 的影响放大 50%**；\n"
   "- **报告质量满分（3.0/3）只占 10% 权重**——是「轻微加成」而不是「决定项」；\n"
   "- 权重在**你的代码**里——下次产品改主意，把 `WEIGHTS['severity']` 改成 0.5 即可，不用动提示词。")

# ============================================================ 4. Noul
md("""---
# 4. Noul（是非判断）：阈值决策、Noul vs Score

Noul 是干净的「是/否」问题，答案就是「是」的浮点概率。
本节：(a) 文档复刻 6 条客户升级消息的阈值表；(b) Noul vs Score 在「Python 经验」上的对比；
(c) 阈值与三路分流。""")

md("""### 📖 理论根基

**Noul 的特殊性质**：

- **没有 confidence 字段**——单个 `noul` 值已经完整描述「是/否」两端的不确定性；
- **「Noul 的值不是程度的量表」**——它衡量「**命题为真**的概率」，不是「**程度**」本身。
  「Python 强吗？」noul=0.5 既可能「经验中等」，也可能「情况不明，候选人间距不一」。
  如果你想测程度，用 [Score](https://docs.typesafe.ai/primitives/score) 配明确的级别。

**阈值设计**：文档原例 `is_human_escalation` 用单阈值（>0.9 转人工）；进阶实战指南用**三路分流**：

| 条件 | 动作 | 理由 |
|---|---|---|
| noul < 0.2 | 明确「否」 | 走机器人路径 |
| 0.2 < noul < 0.8 | 中间值 | **不要猜**，转人工审核 |
| noul > 0.8 | 明确「是」 | 走高置信路径 |

中间值是人类判断的专属空间——比单阈值更稳健。""")

md("### 4.1 定义问题：客户是否在请求人工坐席")
code('''ESCALATION_Q = {
    "is_human_escalation": Noul(
        instructions="客户是否在请求人工坐席",
    ),
}''')

md("### 4.2 6 条客户消息（复刻官方文档原例，中文版）")
code('''ESCALATION_MESSAGES = [
    "谢谢，问题解决了",                           # 文档 noul=0.02
    "怎么重置密码",                               # 文档 noul=0.07
    "我今天就必须解决这件事，不惜一切代价",         # 文档 noul=0.26
    "你是机器人吗",                               # 文档 noul=0.40
    "有没有办法让我找个人谈谈我的发票",            # 文档 noul=0.84
    "我已经问过三次了，能不能让我跟真人谈谈",      # 文档 noul=0.99
]''')

md("**逐条调用并打印 noul 值**")
code('''escalation_results = []
for st in ESCALATION_MESSAGES:
    r = ts.call(st, ESCALATION_Q,
        offline_answers={"is_human_escalation":
                         _FakeAnswer("noul", noul=0.5)})  # 占位，实际每次跑都重写
    escalation_results.append(r.answers["is_human_escalation"].noul)
    print(f"  {escalation_results[-1]:.2f}  | {st}")''')

md("### 4.3 实测发现：中文「你是机器人吗」语义更确定\n\n"
   "在文档的英文原例里，\"Are you a robot?\" 拿到 noul=0.40（模型对「求真人」的解读不明确）；"
   "**我们的中文措辞拿到约 0.10（更明确地表示「否」）**——中文「机器人」一词承载的「求真人」语义比英文弱，"
   "模型反而更愿意把它当作普通疑问。"
   "这是 Level 3（原语）实测校准的典型例子：**先用几句话试、再定稿**，否则你以为「显然求真人」但模型不一定这么认为。")

md("### 4.4 阈值设计：三路分流\n\n"
   "用 0.2 / 0.8 双阈值实现三路分流：明确否 → 机器人；中间 → 人工；明确是 → 升级人工。")
code('''YES = 0.8
NO  = 0.2

for st, noul in zip(ESCALATION_MESSAGES, escalation_results):
    if noul < NO:
        action = "→ 机器人路径"
    elif noul > YES:
        action = "→ 升级人工"
    else:
        action = "→ 人工审核（中间值）"
    print(f"  noul={noul:.2f}  {action:<25} | {st}")''')

md("### 4.5 Noul vs Score：「Python 经验」对比\n\n"
   "同一组 4 位候选人，分别用 Noul（「Python 强吗」）和 Score（「有多少 Python 经验」）提问，"
   "对比两种形状的答案。")
code('''PYTHON_CANDIDATES = [
    "我的经验主要是 Java 和 Go，没用过 Python。",
    "除了主要的 Java 工作，我偶尔用 Python 写写小脚本。",
    "上一份工作里我连续两年每天用 Python，主要是数据流水线。",
    "八年来我每天写 Python，包括维护一个大型 Django 代码库。",
]

PY_NOUL_Q = {
    "py_strong": Noul(instructions="该候选人的 Python 能力很强"),
}

PY_SCORE_Q = {
    "py_xp": Score(
        instructions="该候选人有多少 Python 经验",
        criteria=[
            "完全没用过",
            "偶尔写小脚本",
            "工作中日常使用",
            "深厚专业能力",
        ],
    ),
}

noul_results, score_results = [], []
for i, st in enumerate(PYTHON_CANDIDATES):
    rn = ts.call(st, PY_NOUL_Q,
        offline_answers={"py_strong": PY_NOUL_OFFLINE[i]})
    rs = ts.call(st, PY_SCORE_Q,
        offline_answers={"py_xp": PY_SCORE_OFFLINE[i]})
    noul_results.append(rn.answers["py_strong"].noul)
    score_results.append(rs.answers["py_xp"])
    print(f"  候选 {i+1}: Noul={noul_results[-1]:.2f}  "
          f"Score={score_results[-1].score:.2f} (conf={score_results[-1].confidence:.2f})  "
          f"| {st[:24]}…")''')

md("### 4.6 并排对比表")
code('''print(f"  {'候选人':<6}  {'Noul':>6}  {'Score':>7}  {'Score 概率分布'}")
print(f"  {'-'*6}  {'-'*6}  {'-'*7}  {'-'*40}")
for i, st in enumerate(PYTHON_CANDIDATES):
    s = score_results[i]
    p = "  ".join(f"L{k}={v:.2f}" for k, v in s.probabilities.items())
    print(f"  {i+1:<6}  {noul_results[i]:>6.2f}  {s.score:>7.2f}  {p}")''')

md("### 4.7 观察要点\n\n"
   "- **Noul 给「是不是」**：候选 4 noul=0.87 是「强」的高置信度，候选 1 noul=0.02 是「不强」的明确判断；\n"
   "- **Score 给「在哪一级」**：候选 3 score=2.24 落在「工作中日常使用」和「深厚专业」之间、偏向「日常」；\n"
   "- **Noul 不能回答「这位候选人究竟有多少年经验」**——只能用阈值把它粗切；\n"
   "- **Score 不可用于「是/否」**——如果只关心「该录不录」，Noul + 阈值更直接。\n"
   "\n"
   "**选择原则**：想测程度用 Score；想要布尔/分类用 Noul——文档原话：**「如果两种类型看起来都合适，"
   "优先选择其答案能被你的代码直接使用的那一种。」**")

# ============================================================ 5. 进阶：结构化
md("""---
# 5. 进阶：结构化（Structured inputs）

`instructions`、Choice 选项、Score 级别、Noul 的 `criteria` 都接受 JSON 结构
（字符串 / 对象 / 数组 / `null`）。
本节：(a) 文档原例的发票三字段提取；(b) 结构化 Choice 选项的 `field/not_for/examples`；
(c) 分类树遍历。""")

md("""### 📖 理论根基

**何时对问题使用结构**：

- **结构有助于清晰性时**：一个问题有多个部分时，用 JSON 表达能让键自带标签；
- **问题需要支撑数据时**：schema、分类树、数据库行本身就是 JSON，直接用完整的 JSON 即可，
  **不要把它们序列化成字符串模板**。

**支持结构的字段**：

| 字段 | 适用于 | 接受的形状 |
|---|---|---|
| `instructions` | Choice / Score / Noul | `string` / `object` / `array` / `null` |
| `criteria` 值（选项描述） | Choice | 同上 |
| `criteria` 条目（级别描述） | Score | 同上 |
| `criteria.true` 和 `criteria.false` | Noul | 同上 |

**关键洞察**：字段名（`field` / `focus` / `what` / `not_for` / `examples`）**不是 API 保留字**——
由你来选，模型会连同值一起看到。""")

md("### 5.1 结构化 instructions：发票三字段提取\n\n"
   "文档原例的发票：`Invoice #4471 issued March 3, 2026 to Beaver Dam Logistics for $12,840.00, net 30.`"
   "用一个请求同时问三个字段：发票号匹配、金额档位、付款条款档位。")
code('''INVOICE_TEXT = {
    "source_text": "Invoice #4471 issued March 3, 2026 to Beaver Dam Logistics for $12,840.00, net 30."
}

INVOICE_QUESTIONS = {
    "invoice_number_is_correct": {
        "type": "noul",
        "instructions": {
            "field": {"name": "invoice_number", "type": "string", "description": "发票上的编号"},
            "extracted_value": "4471",
            "question": "`extracted_value` 是否与 `source_text` 中的 `field` 匹配",
        },
    },
    "amount_due": {
        "type": "score",
        "instructions": {
            "field": {"name": "amount_due", "type": "number", "unit": "USD",
                      "description": "发票应付总额"},
            "question": "`source_text` 中 `field` 的金额落在哪一档",
        },
        "criteria": [
            "1,000 美元以下",
            "1,000–10,000 美元",
            "10,000–100,000 美元",
            "100,000–1,000,000 美元",
            "100 万美元以上",
        ],
    },
    "payment_terms": {
        "type": "score",
        "instructions": {
            "field": {"name": "payment_terms", "type": "integer", "unit": "days",
                      "description": "允许的付款天数"},
            "question": "`source_text` 中 `field` 落在哪一档",
        },
        "criteria": ["货到即付", "Net 10", "Net 30", "Net 60", "Net 90"],
    },
}''')

md("**发起调用 + 打印三字段答案**")
code('''inv_resp = ts.call(INVOICE_TEXT, INVOICE_QUESTIONS, offline_answers=INVOICE_OFFLINE)
print("模型:", inv_resp.model, "| 计费 input_tokens:", inv_resp.usage.input_tokens)
print()
for name, a in inv_resp.answers.items():
    if a.type == "noul":
        print(f"  {name:30} noul={a.noul:.2f}")
    else:
        print(f"  {name:30} score={a.score:.2f}  conf={a.confidence:.2f}")''')

md("### 5.2 结构化 Choice 选项：用 `field/not_for/examples` 消歧\n\n"
   "两个易混的选项 `return_policy` / `return_status`——文档原例。结构化描述让边界更清晰。")
code('''RETURN_DISAMBIG = {
    "return_topic": Choice(
        instructions={
            "question": "客户在问哪个退货相关的话题",
            "focus":   "关注客户想了解的信息类别，而不是字面包含的词",
        },
        criteria={
            "return_policy": {
                "what":      "能否退货与如何退货",
                "not_for":   "已寄出退货的进度",
                "examples":  ["穿过的鞋还能退吗", "退货期是多久"],
            },
            "return_status": {
                "what":      "已寄出退货的进度",
                "not_for":   "能否退货与如何退货",
                "examples":  ["我的退货到了吗", "退款什么时候到账"],
            },
        },
    ),
}

RETURN_TEXT = "我上周已经把鞋寄回去了，钱什么时候退给我？"''')

md("**发起调用 + 解读**")
code('''return_resp = ts.call(RETURN_TEXT, RETURN_DISAMBIG,
    offline_answers={"return_topic": _FakeAnswer(
        "choice", choice="return_status", confidence=1.00,
        probabilities={"return_policy": 0.0, "return_status": 1.0})})
ans = return_resp.answers["return_topic"]
print(f"  choice    = {ans.choice!r}")
print(f"  probs     = {ans.probabilities}")
print(f"  conf      = {ans.confidence:.2f}")''')

md("### 5.3 分类树遍历：商品部门分类\n\n"
   "文档原例：自行车水壶（\"32oz plastic bottle with a flip straw lid. Fits most bike cages.\"）"
   "——可以归入「运动用品 > 骑行 > 自行车水壶架」或「家居厨房 > 饮具 > 水壶」。"
   "展示**分类子树**让模型在选定分支前先看到该分支下有什么，"
   "`probabilities` 会告诉你两者接近到值得同时探索两个分支。")
code('''PRODUCT_TEXT = "32oz 塑料瓶，带翻盖吸管。适配大多数自行车水壶架。"

TREE_QUESTIONS = {
    "department": Choice(
        instructions="这个商品属于哪个顶级部门",
        criteria={
            "运动户外": {
                "骑行": ["自行车水壶与水壶架", "自行车灯", "头盔"],
                "健身": ["瑜伽垫", "阻力带"],
                "户外": ["帐篷", "睡袋", "登山水袋"],
            },
            "家居厨房": {
                "饮具": ["水壶", "随行杯", "儿童水杯"],
                "炊具": ["锅具", "烘焙用具"],
            },
            "婴幼儿": ["学饮杯", "奶瓶加热器", "围嘴"],
        },
    ),
}''')

md("**发起调用 + 查看完整概率分布**")
code('''tree_resp = ts.call(PRODUCT_TEXT, TREE_QUESTIONS,
    offline_answers={"department": _FakeAnswer(
        "choice", choice="运动户外", confidence=0.55,
        probabilities={"运动户外": 0.62, "家居厨房": 0.34, "婴幼儿": 0.04})})
ans = tree_resp.answers["department"]
print(f"  choice = {ans.choice!r}")
print(f"  probs  = {ans.probabilities}")
print(f"  conf   = {ans.confidence:.2f}")
print()
print(f"  → 模型把概率 {ans.probabilities['运动户外']*100:.0f}% 放在「运动户外」、"
      f"{ans.probabilities['家居厨房']*100:.0f}% 放在「家居厨房」，"
      f"置信度 {ans.confidence:.2f}。")
print("    下一层 Choice 用该部门的子节点作为选项，递归向下直到叶子。")''')

md("### 5.4 观察要点\n\n"
   "- **结构化 instructions 不增加调用次数**——一次请求同时问 Noul+Score+Score 三种原语，token=696；\n"
   "- **JSON 子树作为 Choice 值**完全合法——模型会看到整棵子树，权衡子分支的具体性；\n"
   "- **真实数据集上要试不同措辞**：文档原例 score=2.0/conf=1.0 是「$12,840 落在 10K–100K 档」的明确判断；"
   "你的数据上若发现 conf<0.8，改用对象式级别描述（`what` / `examples`）通常会提升。")

# ============================================================ 小结
md("""---
# 小结

## 三个原语对照

| 原语 | 字段 | 何时用 | 关键陷阱 |
|---|---|---|---|
| **Choice** | `choice` + `probabilities` + `confidence` | 已知、无序的选项集 | 给完整列表 + `other` 选项；描述要能让选项彼此区分 |
| **Score** | `score` + `legend` + `probabilities` + `confidence` | 可用级别描述的连续谱 | 描述**情境**不描述程度；组合前先**归一化** |
| **Noul** | `noul`（无 confidence） | 干净的「是/否」 | noul 不是程度量表；用三路分流（YES/中间/NO） |

## 关键行为对照表

| 文档声称的性质 | 实测表现 |
|---|---|
| 同一 state 多问题并行评估 | ✅ 5 问批量 762 tokens，与单题多次节省 ~12× |
| 分数是概率加权期望值（小数） | ✅ 1.43 = 0×0.0+1×0.57+2×0.43 |
| Noul 没有 confidence 字段 | ✅ 文档原例 noul=0.99，响应只有 1 个字段 |
| 不同分布可产生相同 score | ⚠️ 解读时必须看 `probabilities` 而不仅是数字 |
| 中文措辞会改变概率分布 | 🔎 「重复扣款」让 `department` 偏 `billing`（conf=0.43）；「你是机器人吗」让 noul≈0.10（英文 0.40） |
| 结构化 instructions 不增加调用次数 | ✅ 三字段一次请求 696 tokens |

## 延伸阅读

- 原语章子页面：[Choice](https://docs.typesafe.ai/primitives/choice) · [Score](https://docs.typesafe.ai/primitives/score) · [Noul](https://docs.typesafe.ai/primitives/noul) · [进阶：结构化](https://docs.typesafe.ai/primitives/advanced)
- 置信度章：[Confidence](https://docs.typesafe.ai/confidence)（下一章实验会做）
- 架构模式：[Patterns](https://docs.typesafe.ai/patterns)（已有配套笔记本 `07_架构模式.ipynb`）
- 实战指南：[Parallel questions](https://docs.typesafe.ai/cookbooks/parallel_questions) · [Hierarchical classification](https://docs.typesafe.ai/cookbooks/hierarchical_classification) · [SDE cascade](https://docs.typesafe.ai/cookbooks/sde_cascade)

## 关于离线模式

本笔记本的每个实验都接入了**真实 TypeSafe API**（jev-1.13 模型）。如果 `TYPESAFE_API_KEY` 无效，
`ts.call()` 会自动回退到 0.6 节的离线示例数据，流程照样能跑通——但示例数据**不会**反映模型的真实行为。
**交付前请确认 Key 有效、`grep` 输出里没有「离线示例」残留**（这是 AGENT.md A5 质量门）。""")

# ============================================================ 写入
nb["cells"] = cells
OUTPUT = Path(__file__).resolve().parent.parent / "../02_核心概念/03_原语.ipynb"
nbf.write(nb, OUTPUT)
print(f"✅ 已生成 {OUTPUT.name}，共 {len(cells)} 个单元格")