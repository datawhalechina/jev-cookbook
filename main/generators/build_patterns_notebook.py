#!/usr/bin/env python3
"""生成《TypeSafe 架构模式实验》Jupyter notebook（中文场景 · 细粒度分步版）。"""
from pathlib import Path

import nbformat as nbf

nb = nbf.v4.new_notebook()
cells = []
md = lambda s: cells.append(nbf.v4.new_markdown_cell(s))
code = lambda s: cells.append(nbf.v4.new_code_cell(s))

# ============================================================ 封面
md("""# TypeSafe 架构模式实验（Architectural Patterns Lab）

针对官方文档 **[架构模式](https://docs.typesafe.ai/patterns)** 章节的可运行实验笔记，
用真实的 TypeSafe API（Jev 模型）逐一验证四种架构模式。
全部实验使用**中文场景与中文提示词**。中文翻译版文档见
[datawhalechina.github.io/jev-cookbook](https://datawhalechina.github.io/jev-cookbook/patterns/)。

## 笔记本结构

| 章节 | 内容 | 实验 |
|---|---|---|
| 0. 准备 | 安装库、配置客户端、连通性测试 | — |
| 📖 理论速览 | System One / 状态 / 原语 / 置信度 / 三种架构（提炼自官方概念章） | — |
| 1. 推测性扇出 | 一次请求发多个问题（含投机问题），代码决定哪些相关 | 中文工单分诊：5 问批量 + 批量 vs 逐条计时 |
| 2. 置信度门控路由 | 答案告诉你"是什么"，置信度告诉你"是否行动" | 语音银行指令：0.6 / 0.85 双阈值门控 |
| 3. 复合评分 | 拆成原子评分，代码里用权重组合 | 中文简历筛选：两套权重 → 排名反转 |
| 4. 意图路由 | 先分类，再路由到确定性代码 / 专家 LLM / 人工 | 客服消息：5 条消息的路由器 |

每个模式按固定节奏展开：**原理 → 理论根基 → 定义数据 → 定义问题 → 调用 → 解读结果**，
每个单元格只做一件事，可直接顺着跑完（约 19 次 API 调用）。

## 运行要求

- Python ≥ 3.10（官方 SDK 要求；macOS 系统自带 python3 是 3.9，装不上 SDK）
- 一个 TypeSafe API Key（[console.typesafe.ai/keys](https://console.typesafe.ai/keys) 获取）

**推荐：一键创建本地环境**（在本 notebooks 目录下）

```bash
./setup_env.sh                                  # 创建 .venv：Python 3.12 + 全部依赖
export TYPESAFE_API_KEY=你的key
.venv/bin/jupyter lab 07_架构模式.ipynb
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

md("### 0.6 各实验的离线示例数据\n\n"
   "下面是四个实验预置的「文档风格」示例答案，**仅在上面显示 Key 无效时才会被用到**。"
   "数值是根据文档示例与实测经验手工拟制的，保证后续分析代码的输出形态与真实运行一致。")
code('''# 实验 1：支持工单（5 个问题的示例答案）
TICKET_OFFLINE = {
    "category": _FakeAnswer("choice", choice="billing", confidence=0.79,
        probabilities={"billing": 0.84, "account": 0.07, "bug_report": 0.09, "feature_request": 0.00}),
    "bug_severity": _FakeAnswer("score", score=1.84, confidence=0.77,
        probabilities={0: 0.05, 1: 0.26, 2: 0.69},
        legend={0: "外观问题；不影响功能",
                1: "功能受损或降级；存在变通方案",
                2: "阻塞性问题；没有任何变通方案"}),
    "has_reproducible_steps": _FakeAnswer("noul", noul=0.11),
    "refund_requested": _FakeAnswer("noul", noul=0.18),
    "frustration": _FakeAnswer("score", score=1.00, confidence=1.00,
        probabilities={0: 0.00, 1: 1.00, 2: 0.00},
        legend={0: "平静、就事论事", 1: "有些沮丧但仍然礼貌", 2: "非常愤怒"}),
}

# 实验 2：语音银行（4 条指令的意图答案）
BANK_OFFLINE = [
    {"intent": _FakeAnswer("choice", choice="check_balance", confidence=1.00,
        probabilities={"check_balance": 1.00, "approve_transfer": 0.00, "other": 0.00})},
    {"intent": _FakeAnswer("choice", choice="approve_transfer", confidence=1.00,
        probabilities={"check_balance": 0.00, "approve_transfer": 1.00, "other": 0.00})},
    {"intent": _FakeAnswer("choice", choice="other", confidence=1.00,
        probabilities={"check_balance": 0.00, "approve_transfer": 0.00, "other": 1.00})},
    {"intent": _FakeAnswer("choice", choice="other", confidence=0.55,
        probabilities={"check_balance": 0.02, "approve_transfer": 0.43, "other": 0.55})},
]

# 实验 3：简历（3 位候选人在 4 个维度上的示例分）
RESUME_OFFLINE = {
    "张伟（资深 IC 型）": dict(python_depth=4.0, team_leadership=1.0, system_design=2.8, generalist=1.1),
    "李强（管理者型）":   dict(python_depth=1.2, team_leadership=4.0, system_design=3.5, generalist=1.8),
    "王雪（均衡成长型）": dict(python_depth=2.9, team_leadership=1.4, system_design=1.2, generalist=2.0),
}

# 实验 4：客服路由（5 条消息的意图 + 复杂度示例答案）
ROUTER_OFFLINE = [
    dict(intent=("order_status", 0.96), complexity=0.15),
    dict(intent=("product_question", 0.89), complexity=0.51),
    dict(intent=("return_exchange", 0.91), complexity=0.83),
    dict(intent=("complaint", 0.90), complexity=2.41),
    dict(intent=("product_question", 0.26), complexity=0.40),
]''')

# ============================================================ 📖 理论速览
md("""---
# 📖 理论速览：读懂实验需要的核心概念

以下内容提炼自官方文档的概念章节（[System One](https://docs.typesafe.ai/concepts/system-one) ·
[状态](https://docs.typesafe.ai/concepts/state) · [原语](https://docs.typesafe.ai/primitives) ·
[置信度](https://docs.typesafe.ai/confidence) · [如何构建](https://docs.typesafe.ai/concepts/how-to-build-with-system-one)；
中文版见镜像站对应页面）。

## System One：为软件做决策的"系统 1"

名称源自丹尼尔·卡尼曼《思考，快与慢》推广的概念：**系统 1 思维快速而直观，系统 2 更慢、更审慎**。
System One 模型就是 AI 中的"系统 1"——它和 LLM 一样能理解自然语言，但不撰写回复、
不产出代码、不生成推理过程解释，只返回**类型化的决策和概率**（约 150ms 量级）。

它有两条关键性质：

- **校准（calibrated）**：模型概率针对实际结果优化，以反映真实的不确定性。
  注意校准是在**成组的预测**上度量的——它并不保证单个答案一定正确；
- **受限输出**：答案空间由你通过原语定义，模型只能在给定选项里表态。

| 原语 | 回答什么 | 返回 |
|---|---|---|
| Choice | 这些选项中的哪一个？ | `choice` + `probabilities` + `confidence` |
| Score | 落在量表的哪一级？ | `score` + `legend` + `probabilities` + `confidence` |
| Noul | 这是否为真？ | `noul`（0–1，"是"的概率本身） |

## 请求模型：状态 + 问题 → 类型化答案

**状态（state）**是你要求模型评估的内容——一条客服消息、一段文字，或应用当前的状况。
可以把它想象成"在请专家小组做判断之前呈给他们的材料"：

| 格式 | 适用情形 | 示例 |
|---|---|---|
| 字符串 | 一条消息、一篇文章 | `"我的卡被重复扣款了。"` |
| 对象 | 具名字段、相关记录 | `{"message": "...", "order_id": "A-104"}` |
| 数组 | 一系列消息或记录 | `["Hi", "客户号 TS1337", "我的卡被重复扣款了"]` |

**每个请求里，所有问题看到的是同一个状态，被独立评估，答案以你选的 ID 返回。**

## 一个问题的解剖

每个问题 = `ID` + `type` + `instructions`（Choice/Score 另有 `criteria`）：

- **ID**：你自己选的键，用于在响应中标识答案；
- **type**：`choice` / `score` / `noul` 之一；
- **instructions**：就状态提出的完整问题，是放置评估逻辑的地方；
- **criteria**：可能的答案——Choice 是选项映射，Score 是有序级别列表，Noul 是对"是/否"的可选澄清。

> 💡 官方提示：**问题 ID 是给你代码用的，不会被发送给模型**。
> 即使 ID 看起来不言自明，也要在 `instructions` 里写出完整的问题。

## 三种软件架构：四种模式存在的意义

| 架构 | 特点 |
|---|---|
| 传统软件 | 简单原语构成的复杂决策树；可靠但读不懂非结构化数据 |
| LLM 智能体 | 自行选择下一步；有人监督时不错，每次循环都带来新的脱轨风险 |
| **AI 驱动的软件** | **代码负责确定性工作并掌控控制流**；模型只出现在需要可编程常识、需要解读非结构化数据的地方，每个 AI 任务保持原子且受限 |

官方概要五条（后面四个模式全是它的展开）：

1. 把控制流、确定性规则和副作用保留在代码中；
2. 把宽泛的判断拆解为**狭窄的、类型化的问题**，给出明确的 instructions 与 criteria；
3. 只给每个问题提供它所需的上下文；
4. 利用**概率与置信度**来行动、请求人工审核或升级处理；
5. 把相互独立的问题**一起提出**，然后在代码中组合它们的答案。""")

# ============================================================ 1. 推测性扇出
md("""---
# 1. 推测性扇出（Speculative fan-out）

> 在单次调用中发送多个问题——包括你**不确定会不会用到**的"投机"问题——并让你的代码决定哪些是相关的。

**为什么值得这么做？**

- 所有问题在同一次请求里**并行评估**，多问几个对响应时间几乎没有影响；
- 传统做法"先问类别、再按需追问"需要串行等待，而扇出把可能的追问**提前**一起发出，
  事后把不需要的答案**直接忽略**即可——忽略一个答案没有任何成本；
- 官方实测（[Parallel questions 实战指南](https://docs.typesafe.ai/cookbooks/parallel_questions)）：
  13 个问题合成一次调用比拆成 13 次调用**便宜 12.2 倍、快 10 倍**，且答案完全一致
  （我们会在 1.6 节自己测一遍）。

**场景**（复刻文档示例，中文化）：一条客服工单进来，需要判断它的类别；
如果碰巧是缺陷报告，还需要严重度；如果是账单问题，还需要知道用户是否要求退款……
这些"如果"对应的问题全部一次发出。""")

md("""### 📖 理论根基

**"一秒判断"原则**（原语章）：System One 为快速、聚焦的判断而生。只要求那些懂行的人
拿到正确上下文后一秒钟内就能做出的判断——"这条消息是否传达了紧迫感？"是好问题；
"分析这条消息并确定最佳行动方案"不是，后者需要缓慢推理，正是要拆成小问题、
在代码中组合答案的信号。

**为什么扇出几乎免费**：请求中的每个问题看到同一个状态、被独立评估，答案按 ID 返回。
因此增加问题的代价约等于零——这正是 1.6 节要实测的性质。""")

md("### 1.1 定义工单（state）\n\n"
   "`state` 是模型要判断的**原始材料**——这里是一条支持工单。"
   "注意这条工单是故意写得很“杂”的：既提到重复扣款，又提到登录问题，还提了个新功能需求，"
   "正好考验分类题的判断力。")
code('''TICKET = (
    "你好，我上周四下的订单（#98423）被重复扣了两次款。另外网站更新之后我的账号一直"
    "登录不上，要是能支持 Apple Pay 就太好了。说实话挺让人生气的。"
)''')

md("### 1.2 定义 5 个问题\n\n"
   "5 个问题里只有 `category` 是**当前必须**的，其余 4 个都是“投机”问题：\n"
   "\n"
   "| 问题 | 类型 | 性质 | 什么时候有用 |\n"
   "|---|---|---|---|\n"
   "| `category` | Choice | 主问题 | 决定工单路由方向 |\n"
   "| `bug_severity` | Score | 投机 | 仅当类别是缺陷报告时需要 |\n"
   "| `has_reproducible_steps` | Noul | 投机 | 仅当类别是缺陷报告时需要 |\n"
   "| `refund_requested` | Noul | 投机 | 仅当类别是账单问题时需要 |\n"
   "| `frustration` | Score | 投机 | 任何类别都可用来决定是否插队人工 |\n"
   "\n"
   "类型速记：**Choice** 从命名选项里选一个；**Score** 沿有序量表打分（返回概率加权期望分，可能是小数）；"
   "**Noul** 回答“是的概率是多少”。")
code('''TICKET_QUESTIONS = {
    "category": Choice(
        instructions="判断这条支持工单的大类",
        criteria={
            "bug_report": "用户报告产品损坏或出现错误",
            "billing": "扣款、发票、退款、订阅",
            "feature_request": "用户请求新功能",
            "account": "登录、权限、个人资料、安全",
        },
    ),
    "bug_severity": Score(
        instructions="所报告问题的严重程度",
        criteria=[
            "外观问题；不影响功能",
            "功能受损或降级；存在变通方案",
            "阻塞性问题；没有任何变通方案",
        ],
    ),
    "has_reproducible_steps": Noul(
        instructions="用户描述了具体的问题复现步骤"
    ),
    "refund_requested": Noul(
        instructions="用户明确要求退款或补偿"
    ),
    "frustration": Score(
        instructions="用户表现出的挫败程度",
        criteria=["平静、就事论事", "有些沮丧但仍然礼貌", "非常愤怒"],
    ),
}''')

md("### 1.3 发起调用（1 次请求，5 个问题）")
code('''ticket_resp = ts.call(TICKET, TICKET_QUESTIONS, offline_answers=TICKET_OFFLINE)
print("模型:", ticket_resp.model, "| 计费 input_tokens:", ticket_resp.usage.input_tokens)''')

md("### 1.4 查看全部答案\n\n"
   "所有问题都拿到了类型化的答案。注意观察：\n"
   "- 选择题给了完整概率分布，而不只是一个获胜选项；\n"
   "- 打分题的 `score` 是概率加权期望值，可能是 1.68 这样的小数；\n"
   "- 是非题的 `noul` 值本身就是“是”的概率。")
code('''for name, a in ticket_resp.answers.items():
    if a.type == "choice":
        print(f"  {name:24} choice={a.choice:<16} confidence={a.confidence:.2f}  {a.probabilities}")
    elif a.type == "score":
        print(f"  {name:24} score={a.score:.2f}        confidence={a.confidence:.2f}")
    else:
        print(f"  {name:24} noul={a.noul:.2f}")''')

md("### 1.5 投机的兑现：代码只取当前分支需要的答案\n\n"
   "分类结果是账单 → 严重度、复现步骤两个投机答案被直接忽略；只有退款问题被消费。"
   "换一个工单类别，消费的会是另外几个字段——"
   "**这就是扇出模式的核心：问题的全集由请求确定，答案的子集由代码按需取用。**")
code('''category = ticket_resp.answers["category"]
print(f"类别 = {category.choice}（confidence={category.confidence:.2f}）")
print()

if category.choice == "bug_report":
    print("→ 转工程组；严重度 =", ticket_resp.answers["bug_severity"].score,
          "；有复现步骤 =", ticket_resp.answers["has_reproducible_steps"].noul > 0.5)
elif category.choice == "billing":
    refund = ticket_resp.answers["refund_requested"]
    print(f"→ 转账单组；用户明确要求退款 = {refund.noul > 0.5}（noul={refund.noul:.2f}）")
elif category.choice == "feature_request":
    print("→ 记录到需求池")
else:
    print("→ 转账号支持")

frustration = ticket_resp.answers["frustration"]
print(f"挫败度评分 {frustration.score:.2f}（≥1.5 时可插队人工队列）——任何分支都可用")''')

md("""### 1.6 实测：批量 vs 逐条

官方主张批量更便宜也更快。我们用同样的 5 个问题做对照实验：

- A 组：1 次请求带 5 个问题；
- B 组：5 次请求每次只带 1 个问题；

对比总耗时与 `usage.input_tokens`（扣费口径；output tokens 目前免费）。
B 组的 token 明显更多，因为 `state` 要随每次请求重复发送。""")

md("**A 组：一次批量调用**")
code('''if TS.offline:
    print("（离线示例模式：跳过计时对比。真实 Key 下本单元格会输出两侧的耗时与 token 对比。）")
else:
    t0 = time.perf_counter()
    batch = client.system_one(TICKET, TICKET_QUESTIONS)
    batch_time = time.perf_counter() - t0
    batch_tokens = batch.usage.input_tokens
    print(f"批量 1 次(5 问): {batch_time:.2f}s, input_tokens={batch_tokens}")''')

md("**B 组：逐条调用 5 次**")
code('''if TS.offline:
    print("（离线示例模式：跳过。）")
else:
    t0 = time.perf_counter()
    per_call_tokens = 0
    for name, q in TICKET_QUESTIONS.items():
        r = client.system_one(TICKET, {name: q})
        per_call_tokens += r.usage.input_tokens
    split_time = time.perf_counter() - t0
    print(f"逐条 5 次(各1问): {split_time:.2f}s, input_tokens={per_call_tokens}")''')

md("**对比结论**")
code('''if TS.offline:
    print("（离线示例模式：跳过。）")
else:
    print(f"→ 逐条是批量的 {split_time / batch_time:.1f}x 耗时、{per_call_tokens / batch_tokens:.1f}x token")''')

# ============================================================ 2. 置信度门控
md("""---
# 2. 置信度门控路由（Confidence-gated routing）

> 答案告诉你**是什么**；置信度告诉你**要不要行动**。

分类题的 `confidence` 是独立于选项之外的第二维信息。文档的语音银行示例给出了一个经典的双阈值设计：

| 条件 | 动作 | 理由 |
|---|---|---|
| confidence < 0.6（任何意图） | 转人工 | 模型真的不确定，别猜 |
| `check_balance`，≥ 0.6 | 直接执行 | 低风险：错了不过是再听一遍余额 |
| `approve_transfer`，0.6 – 0.85 | 请用户确认 | 高风险 + 中等置信度，先核实 |
| `approve_transfer`，> 0.85 | 自动批准 | 高风险 + 高置信度 |

**核心思想：阈值跟着操作的风险走，而不是一个全局数字。**
同一个 0.7 的置信度，对"播报余额"足够行动，对"转出钱"就必须再确认。

> 🔎 **实测发现（jev-1.13）**：官方示例里 `approve_transfer` 的 0.6–0.85「请用户确认」区间
> 在实测中很难命中——模型对可解析的意图极其笃定（含"转账"字样的中文含糊表达同样全部落在
> 0.9 以上），解析不出的则落在低置信度的 `other`。这正是该模式的价值：
> 门控是为模型行为分布的变化预留的安全网，代码路径要备好，哪怕日常触发的是另外三条。""")

md("""### 📖 理论根基：置信度从哪来（置信度章）

- 所有 **Choice / Score** 答案都带 `probabilities`——选项或等级上的完整概率分布。
  **分布的形状才是不确定性的完整描述**：越集中于单一结果越确定，越平坦越不确定；
- `confidence` 是把这个形状**压缩成 0–1 单值**的统计量，让你不必自己计算就能设阈值；
  **Noul 不带 confidence**——它的 `noul` 值本身就是"是"的概率；
- **"我不知道"是一个有用的信号**：一个无法表达真实不确定性的系统（无论人还是机器）都无法被信任；
- 低置信度的具体含义：Choice → 没有任何选项明显胜出；Score → 等级含糊、多维，
  或状态里信息不足；
- 官方三路径：**高**→自动执行；**中**→谨慎推进（请用户确认/标记审核/补充信息）；
  **低**→不要行动（转人工/请求澄清/回退其他系统）。""")

md("### 2.1 定义 4 条语音指令\n\n"
   "覆盖四种典型情况：**明确低风险**（查余额）、**明确高风险**（批准转账）、"
   "**无关意图**（放音乐）、**语义含糊**（“行，就按你说的办”——你能确定“说的”是哪件事吗？）。")
code('''BANK_COMMANDS = [
    "帮我查一下储蓄卡余额",       # 明确的低风险操作
    "请批准那笔待确认的转账",     # 明确的高风险操作
    "来点爵士乐吧",               # 与银行业务无关
    "行，就按你说的办",           # 指代不明——模型应该"不敢确定"
]''')

md("### 2.2 定义意图分类题\n\n"
   "只有一道题：把语音指令归入三类。`other` 选项是关键——给模型一个"
   "“都不是”的出口，它才不会硬把无关指令塞进业务意图里。")
code('''BANK_QUESTIONS = {
    "intent": Choice(
        instructions="用户想执行什么操作？",
        criteria={
            "check_balance": "查询账户余额",
            "approve_transfer": "批准待确认的转账",
            "other": "其他事情",
        },
    ),
}''')

md("### 2.3 定义门控函数\n\n"
   "把上面的阈值表**逐行翻译成代码**。函数只依赖两个东西：分类结果与置信度。")
code('''def handle_bank_command(answer):
    """按官方文档的阈值表路由。answer 是 intent 的 Choice 答案。"""
    if answer.confidence < 0.6:
        return "📞 转人工客服（置信度过低）"
    if answer.choice == "check_balance":
        return "💰 直接播报余额（低风险，0.6 足够）"
    if answer.choice == "approve_transfer":
        if answer.confidence > 0.85:
            return "✅ 自动批准转账（高风险 + 高置信度）"
        return "❓ 请用户确认：「您是要批准这笔转账吗？」"
    return "📞 转人工客服（其他意图）"''')

md("### 2.4 运行：观察同一套门控对不同指令的决策\n\n"
   "每条指令独立调用一次（不同 `state` 之间不能合并请求）。")
code('''for cmd, off in zip(BANK_COMMANDS, BANK_OFFLINE):
    resp = ts.call(cmd, BANK_QUESTIONS, offline_answers=off)
    intent = resp.answers["intent"]
    print(f"「{cmd}」")
    print(f"   意图 = {intent.choice:<16} confidence = {intent.confidence:.2f}")
    print(f"   决策 → {handle_bank_command(intent)}")
    print()''')

md("""**观察要点**

- 前两条指令置信度接近 1，分别走了"低风险直接执行"与"高风险自动批准"；
- 无关指令被 `other` 选项接住，转人工；
- 含糊指令「行，就按你说的办」置信度落到了 0.6 以下——**模型自己承认不确定**，
  被 <0.6 的兜底门拦下。这就是置信度作为"第二决策轴"的价值。""")

# ============================================================ 3. 复合评分
md("""---
# 3. 复合评分（Composite scoring）

> 把一个复杂判断拆成**原子化的评分**，再与你在代码中掌控的**权重**组合。

**为什么值得这么做？**

- 直接让模型"给这个人打个综合分"，等于把你的用人标准埋进提示词里，换岗位就要重写；
- 拆成原子维度后，模型只做它擅长的**客观评估**（每个维度独立打分，互不干扰），
  而权重（多看重管理、多看重架构）完全留在你的代码里；
- 换岗位 = 换一组权重，评分结果可以复用，不用重新调用模型。

**关于 score 的返回值**：`score` 不是整数档位，而是概率加权的**期望值**（例如 3.42 表示
模型认为介于第 3、4 档之间且略偏 4 档）。做加权前先把各维度除以最高档归一化到 0–1。

**场景**（复刻文档示例，中文化）：3 份工程岗简历，4 个维度（Python 深度 / 团队管理 /
系统设计 / 泛用工程），分别按"资深 IC"和"工程经理"两套权重排序。""")

md("""### 📖 理论根基：score 是概率加权的期望值（Score 章）

`score` 不是整数档位，而是**每个级别编号乘以其概率后相加**的结果。文档示例：

```
probabilities = {0: 0.00, 1: 0.57, 2: 0.43}
score = 0×0.0 + 1×0.57 + 2×0.43 = 1.43
```

1.43 表示模型在级别 1 与 2 之间摇摆、略偏 1 级。`legend` 把级别编号映射回文字描述；
`confidence` 依据分布形状计算——置信度 1.0 表示全部概率集中在一个级别上，
**它描述的是模型答案的确定性，并不保证答案一定正确**。

因此复合评分前要**除以最高档归一化**，否则不同量表的维度之间无法按同一权重比较。""")

md("### 3.1 定义候选人简历")
code('''RESUMES = {
    "张伟（资深 IC 型）": (
        "资深后端工程师，某被广泛使用的 Python ORM 的核心贡献者；"
        "设计过跨区域支付平台的分片架构。非正式地指导初级工程师，"
        "比起做管理更倾向亲自写架构方案。"
    ),
    "李强（管理者型）": (
        "工程经理，管理经验 6 年，目前带 3 个团队。"
        "入行时是 Python 开发，现在仍每周参与代码评审。"
        "主导过单体应用向微服务的迁移，横跨两个业务域。"
    ),
    "王雪（均衡成长型）": (
        "4 年经验。Python 是她的主力语言，写过多个服务和内部工具。"
        "3 人功能小组的技术负责人。参与设计过内部的"
        "事件驱动流水线，喜欢身兼多职。"
    ),
}''')

md("### 3.2 定义 4 维评分量表\n\n"
   "每个维度一道 `Score` 题、5 档描述量表（第 0 档最低，第 4 档最高）。"
   "4 道题放在**同一次请求**里并行评——这其实就是模式 1 的扇出。")
code('''RUBRIC_QUESTIONS = {
    "python_depth": Score(
        instructions="根据这份简历，候选人的 Python 功底有多深？",
        criteria=[
            "未提及 Python 经验",
            "仅提到，没有细节",
            "在项目中使用过，有一些具体细节",
            "主力语言，参与过多个项目",
            "深厚功底：架构、性能优化、类库建设",
        ],
    ),
    "team_leadership": Score(
        instructions="候选人在管理或领导工程团队方面有多少经验？",
        criteria=[
            "未提及管理经验",
            "非正式的导师角色或技术负责人",
            "带领过小团队或项目",
            "管理过有直属汇报的团队",
            "管理过多个团队或整个工程部门",
        ],
    ),
    "system_design": Score(
        instructions="候选人在设计大规模或分布式系统方面有多少经验？",
        criteria=[
            "未提及架构工作",
            "参与过设计讨论",
            "设计过较大系统中的局部组件",
            "主导过重要系统的架构",
            "跨多个领域设计过大规模系统",
        ],
    ),
    "generalist": Score(
        instructions="候选人在工程技术栈上的泛化程度如何？",
        criteria=[
            "只深耕一个领域",
            "能胜任两个相邻领域",
            "能在后端、工具链、基础设施之间灵活贡献",
            "很强的多面手，任何方向都能快速上手",
            "在 4 个以上不同领域交付过成果",
        ],
    ),
}

DIMS = list(RUBRIC_QUESTIONS)   # ['python_depth', 'team_leadership', 'system_design', 'generalist']''')

md("### 3.3 逐人评分\n\n"
   "每位候选人一次请求（4 道题并行），收集 4 个维度的原始分（0–4）。")
code('''raw_scores = {}
for name, resume in RESUMES.items():
    resp = ts.call(resume, RUBRIC_QUESTIONS, offline_answers={
        d: _FakeAnswer("score", score=RESUME_OFFLINE[name][d], confidence=0.8,
                       probabilities={}, legend={i: c for i, c in enumerate(q.criteria)})
        for d, q in RUBRIC_QUESTIONS.items()
    })
    raw_scores[name] = {d: resp.scores[d].score for d in DIMS}

print("原始评分（0–4，概率加权期望值）")
print(f"{'候选人':<14}" + "".join(f"{d:>16}" for d in DIMS))
for name in RESUMES:
    print(f"{name:<14}" + "".join(f"{raw_scores[name][d]:>16.2f}" for d in DIMS))''')

md("""### 3.4 定义两套岗位权重

权重来自文档示例：

- **资深 IC**（一线技术专家）：40% Python + 10% 管理 + 40% 架构 + 10% 泛用；
- **工程经理**：15% Python + 40% 管理 + 20% 架构 + 25% 泛用。

`composite()` 先把每维除以最高档 4 归一化到 0–1，再加权求和。""")
code('''ROLE_WEIGHTS = {
    "资深 IC":  {"python_depth": 0.40, "team_leadership": 0.10, "system_design": 0.40, "generalist": 0.10},
    "工程经理": {"python_depth": 0.15, "team_leadership": 0.40, "system_design": 0.20, "generalist": 0.25},
}


def composite(raw_row, weights):
    """把一行原始评分（0–4）归一化到 0–1 后按权重加权求和。"""
    return sum((raw_row[d] / 4) * w for d, w in weights.items())''')

md("### 3.5 计算综合分并排名\n\n"
   "同一批评分喂给两套权重，观察排名是否反转。")
code('''print(f"{'候选人':<14}" + "".join(f"{role:>12}" for role in ROLE_WEIGHTS))
for name in RESUMES:
    row = {role: composite(raw_scores[name], w) for role, w in ROLE_WEIGHTS.items()}
    print(f"{name:<14}" + "".join(f"{row[r]:>12.3f}" for r in ROLE_WEIGHTS))

print()
for role, w in ROLE_WEIGHTS.items():
    ranking = sorted(RESUMES, key=lambda n: composite(raw_scores[n], w), reverse=True)
    print(f"『{role}』岗位排名: " + " > ".join(ranking))''')

md("### 3.6 换个岗位 = 改一行权重\n\n"
   "假设现在招「首席架构师」，架构能力权重提到 60%——不用重新评分，直接换权重重排。")
code('''w_arch = {"python_depth": 0.20, "team_leadership": 0.10, "system_design": 0.60, "generalist": 0.10}
ranking = sorted(RESUMES, key=lambda n: composite(raw_scores[n], w_arch), reverse=True)
print("『首席架构师』(60% 架构) 排名: " + " > ".join(ranking))''')

# ============================================================ 4. 意图路由
md("""---
# 4. 意图路由（Intent routing）

> 在昂贵/专业的处理器之前放一个快速、廉价的分类器：**确定性代码 → 专家 LLM → 人工**。

**为什么值得这么做？**

并非每个请求都需要同一种处理器，它们的成本与能力完全不同：

| 处理器 | 成本 | 适合 |
|---|---|---|
| 确定性代码（查数据库等） | 几乎为零 | 查询类、流程固定 |
| 专家 LLM（带领域上下文） | 中 | 需要生成回复、有一定判断 |
| 人工客服 | 最高 | 复杂纠纷、情绪升级、模型不确定 |

TypeSafe 作为分类器部署在最前面，用一次廉价的调用来决定"这件事该交给谁"。

**场景**（复刻文档示例，中文化）：客服消息涌入，先分类意图与复杂度，再按规则路由。""")

md("""### 📖 理论根基：代码掌控制权（如何构建章）

System One 的定位是构建 **AI 驱动的软件**而非智能体：它不生成代码、不自行选择下一步动作，
只提供可嵌入软件的 AI 原语，让**代码始终保持控制权**，模型负责对非结构化数据做出常识性判断。

意图路由正是官方概要第 1、4 条的直接应用：**路由决策（控制流）完全在你的代码里**，
模型只负责"这条消息是什么意图、有多复杂"这一个狭窄的语义判断——
把两者分开，系统才既获得语言理解，又不放弃可预测性。""")

md("### 4.1 定义 5 条测试消息\n\n"
   "覆盖五种情况：查订单（确定性）、购前咨询（产品 LLM）、退货（退货 LLM）、"
   "愤怒投诉（应升级人工）、乱码（模型应“不敢确定”）。")
code('''SUPPORT_MESSAGES = [
    "我的订单 #12345 到哪了？三天前就显示发货了。",
    "X 型号的意式咖啡机附赠不锈钢拉花缸吗？",
    "那双跑鞋我想退货，偏小半码。",
    ("这是第三次坏了，客服一直互相推。我要全额退款，让你们经理给我回电话，"
     "不然我就向银行发起拒付了。"),
    "。。。",
]''')

md("### 4.2 定义分类问题\n\n"
   "两道题一次并行评出：\n"
   "- `intent`（Choice）：消息的主要意图，四选一；\n"
   "- `complexity`（Score）：解决该请求的复杂程度，3 档量表。")
code('''ROUTER_QUESTIONS = {
    "intent": Choice(
        instructions="这条客户消息的主要意图",
        criteria={
            "order_status": "询问已有订单的状态",
            "product_question": "购买前咨询产品",
            "return_exchange": "想退货或换货",
            "complaint": "对体验不满，希望得到解决",
        },
    ),
    "complexity": Score(
        instructions="解决该请求的复杂程度",
        criteria=[
            "简单查询或标准流程",
            "需要一定判断或多步流程",
            "特殊情况、边缘案例或需要升级处理",
        ],
    ),
}''')

md("### 4.3 定义三个处理器\n\n"
   "本笔记用打印代替真实后端，但**成本阶梯是真实的**：确定性代码不花钱、"
   "专家 LLM 花小钱、人工最贵。路由的目标就是让大部分流量落在便宜的处理器上。")
code('''def deterministic_order_lookup(msg):
    """订单查询：直接查数据库，不调用任何模型。"""
    return "[确定性代码] 查订单库 → 订单 #12345：已到达本地配送站"


def specialist_llm(kind, msg):
    """带领域上下文的专家 LLM（产品答疑 / 退货流程 / 投诉安抚）。"""
    return f"[{kind} 专家 LLM] 生成针对性回复…"


def human_agent(msg):
    """人工客服：最贵也最可靠，留给复杂与不确定的情况。"""
    return "[人工客服] 创建工单并排队"''')

md("""### 4.4 定义路由函数

规则来自文档示例，注意两条**安全优先**的设计：

- 意图置信度 < 0.5 → 不猜了，直接人工（路由错的代价比人工贵）；
- 投诉类：复杂度 > 1 或置信度 < 0.5 → 升级人工，否则才交给投诉处理 LLM。""")
code('''def route(msg, answers):
    intent, complexity = answers["intent"], answers["complexity"]

    if intent.confidence < 0.5:
        return human_agent(msg)
    if intent.choice == "order_status":
        return deterministic_order_lookup(msg)
    if intent.choice == "product_question":
        return specialist_llm("产品", msg)
    if intent.choice == "return_exchange":
        return specialist_llm("退货", msg)

    # complaint：复杂度高于"多步流程"或置信度不足时升级人工
    if complexity.score > 1 or complexity.confidence < 0.5:
        return human_agent(msg)
    return specialist_llm("投诉处理", msg)''')

md("### 4.5 运行路由器\n\n"
   "每条消息一次调用（intent 与 complexity 两问并行），打印分类结果与最终路由。")
code('''for msg, off in zip(SUPPORT_MESSAGES, ROUTER_OFFLINE):
    resp = ts.call(msg, ROUTER_QUESTIONS, offline_answers={
        "intent": _FakeAnswer("choice", choice=off["intent"][0], confidence=off["intent"][1],
            probabilities={}),
        "complexity": _FakeAnswer("score", score=off["complexity"], confidence=0.85,
            probabilities={}, legend={0: "简单", 1: "多步", 2: "需升级"}),
    })
    intent, complexity = resp.answers["intent"], resp.answers["complexity"]
    shown = msg if len(msg) <= 40 else msg[:40] + "…"
    print(f"「{shown}」")
    print(f"   intent={intent.choice:<16} conf={intent.confidence:.2f}   complexity={complexity.score:.2f}")
    print(f"   → {route(msg, resp.answers)}")
    print()''')

md("""**观察要点**

- 查订单消息走的是确定性代码——这类流量最大的请求完全不花模型的钱；
- 投诉消息复杂度接近 2（"需升级"），被抬到人工；
- 乱码「。。。」的意图置信度只有 0.2 左右，被 <0.5 的门控兜底到人工——
  **分类器可以便宜，但代价错配必须被拦住**。""")

# ============================================================ 小结
md("""---
# 小结

| 模式 | 实验验证的行为 | 代码里的关键点 |
|---|---|---|
| 推测性扇出 | 5 个问题一次请求并行返回；投机答案直接忽略；批量远快于逐条 | 事后按分支取用 `answers` |
| 置信度门控路由 | 同一个意图答案，按 confidence 走多条路径 | 阈值跟操作风险走 |
| 复合评分 | 4 个原子评分 → 代码权重 → 岗位不同排名不同 | `score` 归一化后加权 |
| 意图路由 | 分类器在处理器之前，便宜的先上 | 低置信度兜底人工 |

## 延伸阅读

- 原文与中文版：[Patterns](https://docs.typesafe.ai/patterns) · [中文镜像](https://datawhalechina.github.io/jev-cookbook/patterns/)
- 把模式用到真实数据集：官方 [18 篇实战指南](https://docs.typesafe.ai/cookbooks)（中文版见镜像站「实战指南」）
- 免交互试玩：[Playground](https://console.typesafe.ai/playground)

> ⚠️ 若本笔记在离线示例模式下运行：输出中的数值是内置示例，用于演示代码路径；
> 设置有效的 `TYPESAFE_API_KEY` 后 **Restart & Run All** 即可得到全部真实结果。""")

nb["cells"] = cells
nb["metadata"]["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
nb["metadata"]["language_info"] = {"name": "python", "version": "3.12"}

out = Path(__file__).resolve().parent.parent / "03_架构模式/01_架构模式.ipynb"
with open(out, "w", encoding="utf-8") as f:
    nbf.write(nb, f)
print("written:", out, "| cells:", len(cells))
