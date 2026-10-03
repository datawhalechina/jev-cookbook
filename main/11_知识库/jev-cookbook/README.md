# Jev Cookbook

Jev 相关项目的**文档 + 核心代码**精选包。多个开源仓库的 Markdown 全量收录，代码只取能说明
「状态 → 问题 → 概率 → 动作」这条决策链路的实现，测试、脚手架、依赖锁、数据集、模型权重
一律不收；另附飞书深度文档、公众号文章、第三方评测基准，以及 Laya 本地部署和 Jev 兼容接口示例。

原始来源、版本 commit、各项目未收录清单见 [`SOURCES.md`](SOURCES.md)。

---

## Jev 是什么

Jev 是 TypeSafe AI 的旗舰模型，也是第一个 **System One 模型**：你发给它**状态（state）**
和**类型化问题**，它返回带**概率**和**置信度**的结构化答案。没有文本生成，没有解析。

三种问题原语：

| 原语 | 形态 | 典型用途 |
|---|---|---|
| **Choice** | 在 2–255 个候选里给出分布 | 选模型、分类、选候选 |
| **Score** | 在有序档位上给出分布与期望 | 相关性、严重程度、质量打分 |
| **Noul** | 命题为真的概率（布尔） | 独立判定、证据核查 |

同一请求里的每个问题**相互独立**地看到同一份 state。问题 ID 只用于对齐输入输出，
不是模型指令——要指向 state 里的某个条目，必须在问题文本里写清楚。

关键设计取向：**代码拥有流程，模型只提供可编程的常识**。规则、计算、精确查表留在代码里，
只在需要语义理解的地方调用 Jev。

---

## 从哪开始

看你的目标：

| 你想做的事 | 去这里 |
|---|---|
| 先理解 Jev 的编程模型 | [`01-official-docs-zh/concepts/`](01-official-docs-zh/concepts/) |
| 快速建立全局认识（含成本/性能对比） | [`10-feishu-research/`](10-feishu-research/) 三篇深度报告 |
| **看怎么把它接进 Agent 干活** | [`16-wechat-agent-engineering/`](16-wechat-agent-engineering/) 万字工程实践 |
| **看它和专用小模型的实测对比** | [`18-wechat-rerank-experiment/`](18-wechat-rerank-experiment/) Jev vs Reranker 实验 |
| 看从业者视角的务实解读 | [`12-wechat-article/article.md`](12-wechat-article/article.md)、[`17-wechat-silicon-grail/`](17-wechat-silicon-grail/) |
| 看 Jev Cookbook 完整学习路线和项目图文介绍 | [`22-wechat-cookbook-intro/article.md`](22-wechat-cookbook-intro/article.md) |
| **看各家模型横向排名** | [`15-jevbench/`](15-jevbench/) 第三方评测基准 |
| 看一次完整的入门讲座 | [`14-feishu-lecture/`](14-feishu-lecture/) |
| **了解 / 本地调用开源 Laya** | [`laya-model/README.md`](laya-model/README.md)：参数架构、Jev 对比、MPS 部署、HTTP 接口；[`微调与数据构建方案`](laya-model/FINETUNING.md) |
| 找「还有哪些资料值得读」 | [`13-feishu-cookbook-plan/`](13-feishu-cookbook-plan/) 精选资料清单 |
| 直接开工写代码 | [`01-official-docs-zh/introduction/quickstart.md`](01-official-docs-zh/introduction/quickstart.md)、[`01-official-docs-zh/api.md`](01-official-docs-zh/api.md) |
| 找「我这个场景该怎么问」 | [`01-official-docs-zh/cookbooks/`](01-official-docs-zh/cookbooks/)（20 篇） |
| 看真实项目怎么组织 | `02` ~ `07`、`11` 各目录，见下方「十八个项目」 |
| 训练自己的决策模型 | [`02-nanojev/`](02-nanojev/) + [`09-typesafe-sdk-python/`](09-typesafe-sdk-python/) |
| 用 Python / JS SDK | [`01-official-docs-zh/sdk/`](01-official-docs-zh/sdk/)、[`09-typesafe-sdk-python/code/`](09-typesafe-sdk-python/code/) |
| 让 AI 代理学会用 Jev | [`06-typesafe-skills/SKILL.md`](06-typesafe-skills/SKILL.md) |

> 中文资料来自社区翻译（`01`），英文原版以 https://docs.typesafe.ai 为准。
> `10`、`12` ~ `18` 为第三方或内部内容，`15` 为独立第三方评测，
> 观点与数据请对照原文自行核验。

---

## 十八个项目

### 01 · 官方文档中文翻译 — `01-official-docs-zh/`

109 页全量中文翻译，路径与原站 URL 一一对应；含静态站点生成器。

- `content/` — 109 页正文。`concepts/`（System One 编程模型、state、用例地图）、
  `primitives/`（三种原语详解）、`cookbooks/`（20 篇实战配方）、
  `patterns/`（意图路由、置信度路由、扇出、复合打分）、`sdk/`、`model-jaggedness/`
- `code/build.py` — 纯标准库的静态站点生成器，`python3 build.py` 一键构建
- 在线版：https://datawhalechina.github.io/jev-cookbook/

**重点看**：`cookbooks/parallel_questions.md`（并行问题为什么比逐个调用快）、
`cookbooks/classification_using_confidence.md`（用置信度分流）、
`concepts/how-to-build-with-system-one.md`。

---

### 02 · NanoJev — `02-nanojev/`

一个 **0.6B 的并行决策模型**复刻：输入状态与问题，输出完整概率分布，**零输出 token 解码**。
同一个 checkpoint 打通四款游戏：ViZDoom Basic、ViZDoom Predict Position、50×50 迷宫、贪吃蛇。

- 对比数据（274 例测试集）：NanoJev 在 Basic 上 **128/128**，Jev 为 **56/128**；
  Predict Position **27/128**，Jev 是 **11/128**
- 数据集：每变体 **18,760 个决策问题**，含 **16,333 个 ViZDoom 问题**
- 骨干 Qwen3-0.6B + 决策头；Choice 用集合注意力 + softmax，Boolean 用 sigmoid，
  Score 返回概率加权的档位
- `docs/` 19 篇（发布说明、输入契约、环境设计）、`research/` 38 篇（训练契约、
  RLCD 理论、算法审计、导航复盘）

**核心代码**（`code/`）：

| 文件 | 作用 |
|---|---|
| `unified_game_pipeline.py` | 采集 / 观测结果 / 策略迭代主流程，被 27 个脚本引用 |
| `train_pipeline_decisions.py` | 训练入口：完整问题微批次、dev 选优、分布指标 |
| `train_unified_games.py` | 四任务统一训练（Maze/Snake/Basic/Predict 权重 1/3,1/3,1/6,1/6） |
| `calibrated_objectives.py` | 评分规则损失：Brier、成对 Brier 策略损失、分组校准损失 |
| `serve_decisions.py` | 常驻推理服务，权重只加载一次 |
| `run_jev_parallel_cases.py` | 对 Jev 的并行问题批量调用 |
| `label_decision_dataset.mjs` | 用 Jev 给数据集打标签 |
| `probe_jev_distributions.mjs` | 探测 Jev 的概率语义 |

`configs/` 保留了四个 demo 的训练/演示配置。

**读法建议**：先 `research/algorithm_training_contract_zh.md` 建立训练全貌，
再看 `calibrated_objectives.py` 理解损失怎么定，最后 `unified_game_pipeline.py` 看闭环。

---

### 03 · jev-trader — `03-jev-trader/`

**每个 Monad 区块做一次决策**的做市机器人。Jev 盯 Kuru 的 MON-USDC 订单簿，
每 ~300 ms 回答一次 buy / sell，每个区块在 touch 内侧一个 tick 挂 post-only 限价单，
赚价差而不是付价差。

- **300 ms 预算**是核心约束：热路径只走两次 RPC —— 一次 `eth_call` 读盘口（公开 RPC 约 18 ms）、
  一次 `eth_sendRawTransaction`。不做 `eth_estimateGas`、不做 `sendRawTransactionSync`、
  不查 gas price
- 无 `PRIVATE_KEY` 时自动 dry-run：真实盘口、真实决策、模拟成交
- 模型切换：`MODEL=jev` + API key 走 Jev，默认 `mock` 是动量启发式替身

**核心代码**（`code/`）：`model.ts`（Model 接口 / JevModel / MockModel）、
`trader.ts`（决策循环、持仓与盈亏）、`market.ts`（Kuru 交互、手编码 batchUpdate）、
`book.ts`（单次 eth_call 读盘口）、`config.ts`。

**看这个项目是为了**：一个把 Jev 放进**硬实时约束 + 资金风险**链路的生产范例——
它讲清楚了延迟预算怎么切、决策失败（late）怎么降级、意图与回执为什么要分开。

---

### 04 · fast-jev-compaction — `04-fast-jev-compaction/`

Claude Code 插件：**用 Jev 决策替代上下文压缩摘要**。每次工具调用与结果都被打一次分，
过期的删掉或截断，**保留下来的保持逐字原样**。

思路差别：常见的压缩让 LLM 总结旧轮次，而摘要是有损的——文件路径、精确报错、约束条件
可能恰好丢掉。这个库**从不改写任何内容**，只删除 Jev 判定不再需要的工具调用与结果；
用户与助手的文本逐字按序保留。

工作方式：

1. 用 `tool_use_id` 配对调用与结果；首条消息和最近 N 条消息**钉住**，永不改动
2. 发给 Jev 的 state 是**至今的完整对话**，但每个工具结果替换成一句短注
   （`ok, 4213 chars (omitted)`）
3. state 按 `maxStateTokens`（默认 25k）分阶段裁剪，逐级加码直到装得下
4. 对每个未钉住的调用问两个 `noul`：**调用**还要留吗？**结果**还需要逐字保留吗？
5. 决策：`keepResult ≥ 阈值` → 全留；否则 `keepCall ≥ 阈值` → 留调用、截断结果；
   都不满足 → 调用与结果一起删
6. 重建消息列表，不留孤立的 tool_result

**核心代码**（`code/`）：`src/compact.ts`（主流程）、`src/state.ts`（state 裁剪与 token 估算）、
`src/client.ts`、`hooks/fast-jev.ts`（Claude Code 挂钩）。

**看这个项目是为了**：`noul` 原语在**上下文治理**上的用法，以及一个很实用的工程判断——
压缩完如果 `reductionRatio < 0.25`，说明不划算，直接用原文或换摘要。

---

### 05 · awesome-jev — `05-awesome-jev/`

Jev 生态的资源索引（72 KB README + 14 个分类页）。分类覆盖：代理决策、校准研究、
分类路由、合规法务、内容审核、数据标注、评估基准、金融交易、游戏仿真、
基础设施与 SDK、科学流水线、打分排序、验证护栏。

**用途**：找同类项目和既有实践，避免重复造轮子。另含 `skill/jev-curation-SKILL.md`——
一套资源策展的方法论，可借鉴到自己的知识库维护。

---

### 06 · TypeSafe 官方 Skill — `06-typesafe-skills/`

官方 Claude Code 插件形式的 Skill（`SKILL.md`），教 AI 代理**如何用 TypeSafe 构建软件**。

要点：把 TypeSafe 当作可组合的编程原语；**活文档才是真相来源**，Skill 只给方向；
从用户想要的行为倒推需要哪些判断；已知规则、计算、精确查表与执行留在代码里。

**用途**：想让自己的 AI 编码代理（Claude Code / 其他）在需要「可编程常识」时自动想到 Jev，
直接把 `SKILL.md` 放进 skills 目录。另含 `plugin.json` / `marketplace.json` 插件清单。

---

### 07 · jev-ultrafast — `07-jev-ultrafast/`

browser-use 官方的**动态索引动作空间**浏览器代理。给一个目标，Jev 选操作和元素，
小 LLM 只在 `TYPE_TEXT` 时才生成文本。

- 实测：**苏黎世 → 伦敦** Google Flights 搜索 **7.1 秒**（含真实文本生成与加载等待）
- 动作空间：`CLICK`、`TYPE_TEXT`、`SELECT`、`SCROLL_UP/DOWN`、`WAIT`、`DONE`、`BLOCKED`，
  且**只提供当前支持的操作与目标**
- 观测每次生成新的元素表（`[1] button Change ticket type · Round trip` …），
  目标问题带投机性：**操作与目标两个决策走一次网络往返**，每个目标头只含兼容元素
- 策略里没有任何站点专用脚本或预置字段字符串

**核心代码**（`code/`）：`agent.py`（主循环）、`model.py`（Jev 交互）、
`browser.py`、`questions.py`、`examples/flights.py`。
`docs/performance.md` 有完整测量方法与数据。

**看这个项目是为了**：动作空间**动态索引**的范式——把候选集从页面实时生成，
而不是固定枚举，这是 Jev 类模型最自然的落地形态之一。

---

### 08 · eve 的决策模型研究 — `08-eve-decision-models/`

Vercel eve 仓库中的一篇研究文档（Apache-2.0）：**把 Jev 用作模型路由器**
（LLM-as-judge 的判别场景）。

- 建议在 `eve/models` 暴露 `auto`、在 `eve/ai` 暴露独立 `evaluate`，
  两者都建立在 AI SDK 的 `experimental_evaluate` 之上
- 三种原语到 AI SDK 类型的映射表（Choice/Score/Noul → choice/score/boolean），
  以及各自适合的 eve 应用
- 重要边界：**Choice 与 Score 的分布在 AI SDK 契约里是可选的**（语言模型适配器不产出分布），
  只有布尔概率是必需的；TypeSafe 单独的 confidence 统计留在 provider metadata。
  因此通用路由器**不能跨 provider 承诺置信度阈值**
- 约束输出能防止编造选项名，但**不保证选项正确**；校准描述的是数据集上的行为，
  不是单次答案的确定性

**看这个项目是为了**：如果你要在自己的 agent 框架里做**自动选模型**，
这篇给了完整的接口边界、生命周期（决策挂在 `step.started`，只持久化选项 key）
和范围边界（不引入 TypeSafe 专有的 decide 函数、不做 provider fallback）。

---

### 09 · typesafe-sdk-python — `09-typesafe-sdk-python/`

官方 Python SDK 源码（v0.7.0）+ 变更日志。完整覆盖 `_core/`（传输、重试、错误、
端点、问题类型、响应类型）、`client/sync/` 与 `client/aio/` 两套客户端、`_schemas/`。

**用途**：文档说不清的地方直接读实现——重试策略、超时、错误分类、
请求体怎么组装、响应怎么校验，这里有确定答案。

---

### 10 · 飞书深度研究报告 — `10-feishu-research/`

三篇独立撰写的 Jev 研究报告，合计约 9.7 万字，角度互不重复。**建议先读这个建立全局认识，
再进 `01` 看官方口径。**

| 文件 | 侧重 |
|---|---|
| `01-算法原理-实验对比-成本优势.md`（5.6 万字） | 最全的一篇。术语消歧、System One 技术栈、非自回归并行采样、RLCD、三种原语、置信度；官方并排演示与 711 案例评测的准确率结构；速率优势的证据链 |
| `02-系统一架构-性能基准-工程落地.md`（1.6 万字） | 表征降维的设计哲学、性能基准、工程落地价值与成本模型（含 15 张公式图） |
| `03-从生成语言转向机器决策.md`（2.5 万字） | 从「生成 token」到「类型化决策」的范式转换，接口约束与能力边界 |

三篇均为**第三方研究**，含大量外部引用（角标指向原始来源），部分数据来自官方口径。
与官方文档（`01`）冲突时以官方为准。

**注意**：这三篇出自个人飞书 wiki，非公开仓库，包内已全文收录（含公式图），
请勿对外分发。

---

### 11 · typesafe-mario — `11-typesafe-mario/`

让 Jev **直接操作初代《超级马力欧兄弟》NES 手柄**的实验性控制器。
架构一句话讲完：`NES 模拟器 → 遥测/RAM 解析 → 结构化 JSON → Jev Choice → 手柄输入`。

**关键设计：模型看不到截图。** 接收方不是画面，而是一份**以对象为中心**的紧凑 JSON——
马力欧的运动与跳跃轨迹、前方敌人与接触时机、地形几何、**实测响应延迟**、
最近几次操作的结果、关卡进度。本地 tile 网格只在调试日志与 UI 里出现，不重复塞进模型输入。

- 动作集刻意做小：`noop`、`right`、`right_jump`、`right_run`、`right_run_jump`、`jump`、`left`
- 每 8 个模拟器帧决策一次，`runner.py` 把每次决策写成 `artifacts/run-<时间戳>.jsonl`：
  延迟、动作概率、置信度、规范化模型状态、原始调试状态、游戏结果
- 附带一个 `HeuristicPolicy` 作为对照，方便判断模型到底贡献了什么

**核心代码**（`code/`）：

| 文件 | 作用 |
|---|---|
| `state.py` | 28 KB 的 RAM 解析器：从内存转成结构化 `MarioSnapshot` |
| `policy.py` | `TypeSafePolicy`（真实调用，含 `Choice`/`Score`/`Noul` 组合）+ `HeuristicPolicy` 对照 |
| `runner.py` | 主循环：环境创建、决策记录、实时面板、回合管理 |
| `actions.py` | 动作枚举与给模型看的动作描述 |

**看这个项目是为了**：**状态表示**这一课。同一个游戏，喂截图和喂结构化对象是两条完全不同的路——
这里把"模型该看什么"当作核心工程问题来解，并把响应延迟也一并测出来喂回去。

> 仓库不含任何 Nintendo ROM 或游戏数据，需自备合法游戏文件。

---

### 12 · 公众号文章 — `12-wechat-article/`

腾讯技术工程发表的从业者视角解读：《聊聊最近爆火的 Jev 模型，到底是个啥？》，
约 7000 字。作者是 mason（Principal Research Leader），**自己动手做了一个网页小游戏**
验证 Jev 到底在其中起什么作用。

与 `10` 的三篇研究报告互补——那三篇偏资料综述，这篇偏**亲手试过之后的判断**：

- **诚实区分「说明了什么」和「不能说明什么」**：视频能说明模型的选择确实驱动了游戏、
  响应足够支持回合制交互；不能说明 Jev 比 GPT 更会玩。作者明确写了"没有完成有效的双模型实测，
  所以这里不放胜负和性能结论"
- **纠正两个常见误解**：概率（如 95%）和置信度（如 93%）是两个不同的数，也都**不是通关概率**；
  每秒做十次决策**不等于**接管每一帧的物理和控制
- **承认自回归模型的进步**：结构化输出已能约束字段与枚举，不能拿"通用模型总要写一大段话"当比较前提——
  真正的差别在调用频率与整体场景
- 四类落地场景（游戏 AI、Agent 路由与护栏、高吞吐分类、多指令并行解析），
  以及未来判断：**最大竞争压力来自两边**（大模型厂商 + 传统专用分类器），
  Jev 的位置在两者之间

三张配图已本地化：创始人的发布推文截图、游戏循环示意图（读局面 → 选动作 → 看结果 → 再决定）、
browser-use × TypeSafe 的 Ultrafast 演示动图。

**注意**：文章版权归腾讯技术工程所有，包内为存档快照，请勿对外分发。

---

### 13 · 知识库规划与精选清单 — `13-feishu-cookbook-plan/`

这份知识库**自身的规划文档**，外加一篇深度报告与两份资料清单。
它回答的是「这个包为什么是现在这个结构」，也是继续扩充时的路线图。

`01-Jev-cookbook-知识库初步.md`：

- **Day1 调研目标**：算法原理与区别、实验与速率对比、成本测算、使用场景预测——
  这四条正是包内 `10` 三篇报告各自的章节主线
- **Day2 任务分工**：8 个应用复现（射击 / 迷宫 / 贪吃蛇+五子棋 / 位置预测 /
  上下文压缩 / browser-use / 数独 / 马里奥）各自的对口仓库与负责人，附官网基础实践分工图
- **Day3 计划**：国产模型横向比拼（K3、GLM5.3、Step5、Qwen3.8-Max、DeepSeek V4.1、豆包2.1-Pro），
  记录不同领域的判断效果、token 与费用（含思考开关）
- **成员提交的资料清单**，逐条标注「已收录 / 已收录于 `10` / 无权访问」

其中最有复用价值的是**两份精选资料清单**——不只是罗列，而是写了推荐理由与边界：

| 清单 | 内容 |
|---|---|
| 官方资料怎么读 | AI Primer（RLHF/RLVR/RLCD 与概率校准）、Confidence、How to build with TypeSafe、Patterns 四篇官方文档，各自「讲了什么」与「缺什么」 |
| 第三方资料怎么读 | Sean Goedecke 两篇（机制辨析首选 / 带代码的实践首选）、LangChain 的 Harness 教程；**明确标注了哪些结论属于作者推断而非事实** |

`02-Jev技术深度解析与应用前景评估.md`（2.7 万字）——飞书 wiki 中可访问的深度报告，
从「翻译税」（Translation Tax）问题切入，讲并行采样架构、成本优势与多框架代码基线实践。

**另含三份附件**（`files/`）：Jev 决策模型技术构成与独立验证报告（PDF，5 页）、
RLHF 之后 AI 的发展方向详细报告（PDF，9 页）、豆包生成的深度研究报告（HTML，带样式）。

**注意**：本文引用的 5 篇飞书文档因无权访问未能收录（已在正文逐条标注去向）；
内容含团队成员贡献材料，请勿外传。

---

### 14 · JEV 模型应用入门与实践 — `14-feishu-lecture/`

一次技术讲座的**高保真整理稿**（约 4500 字），按讲座脉络整合，标注了每章对应的视频时间点
（如 `*本章对应视频 00:00 - 02:43*`）。与 `10` 的研究报告不同，这份是**动手视角**：
从模型特性推到 LangChain 集成，再到实际演示。

主线是**意图识别**——讲者认为这是 Jev 最自然的落点：「并行、便宜、快」三个特性刚好对上。
然后展开 LangChain 的两个集成场景：

- **Model Routing**：判断何时用强模型、何时用便宜模型，本质是个 choice 问题
- **Auto Mode 工具审批**：同一个 `Delete Backup` 工具，在生产环境应阻断、
  在 Staging 清过期内容应放行——文章用一组对比演示展示这个差异，并附内嵌对比表

另含注册流程与费用说明（输入每百万 token $0.042、输出免费、注册赠 $5 额度），
以及行业展望：预期大厂会在工具调用、评估评测、结构化输出三个垂直方向加快跟进。

5 张配图已本地化（LangChain 博文、三种原语、费用页、Auto Mode 演示、模型路由代码）；
内嵌的对比表已转为 Markdown 表格内联。

**注意**：讲座整理稿，内容涉及内部培训，请勿外传。

---

### 15 · jevbench — `15-jevbench/`

[fstandhartinger/jevbench](https://github.com/fstandhartinger/jevbench)：**独立第三方评测基准**，
给 Jev 类决策模型排名。由 Benchmark Heaven 维护，与 TypeSafe 无隶属关系（Jev 只是被测评的对象之一）。

**JevBench Score** 由四个轴等权（各 25%）几何平均——**弱项会狠拉总分**：

| 轴 | 口径 |
|---|---|
| Intelligence | 加权准确率：hard 30%、easy 14%、standard 28%、judge 28% |
| Calibration | hard 层：ECE + 与精确金标分布的吻合度（只输出标签的系统记 0） |
| Speed | p50 与 p95 得分的均值，对数刻度（0.1 秒 = 100，每慢 10 倍 −20） |
| Cost | **每 1,000 次决策**的美元成本（不是每千 token），$0.001 = 100，每贵 10 倍 −30 |

**当前榜首（v1.2.8，36 行排名）**：Jev 1.13.0 **75.4** · SemIf 74.7 · djev 74.3 ·
openJev Verdict 1.4 72.5 · reflex 4B 71.7 · decision-machine-1 71.5。

**这份基准的严谨之处值得单说**（也是选它的原因）：

- **数据集冻结**：534 次决策、220 道 hard 题（111 公开 + 109 留出），
  在**任何被测系统运行之前**冻结并哈希，公开文件与留出文件都有 sha256
- **交叉评审**：Claude Opus 5 出的题由 GPT-5.6 Sol 盲评，反之亦然；有异议走一轮讨论，
  未通过即丢弃。**没有任何题目因某个被测系统的表现而被选中或删除**
- **成本口径写死**：反复强调 Cost 是"每 1,000 次决策"而非"每千 token"，
  并专门发过一个 v1.2.3 修正版订正三处算错的算术（订正后 15 行变便宜、1 行变贵，**排名不变**）
- **区分 native 与 verbalized**：前四种适配器读模型**自己的**概率分布，
  `openai_compat` 是让模型**写出**概率——两者被明确标注为不同的东西
- **不测不可测的**：两个系统因公开仓库缺模块/404 而明确标注"本轮无法测量"

**收录内容**：全部 17 篇文档（含各版本结果、hard 层构造方法、评分规则）、
公开数据集（easy/standard/original 三个 jsonl）、核心包代码（任务定义、运行器、
评分、指标、v1.2 合成分）、4 种接口范式的适配器（含 `typesafe` 官方接口、本地权重、
OpenAI 兼容）、v1.2 的完整结果与 5 张图表、评分与制图流水线、
被文档引用的组合实验数据（confidence cascade / committee / best-of-n），
以及 `tests/`——README 把其中若干用例当作评分规则的验证依据直接引用。

**看这个基准是为了**：知道**该选哪个模型**不该只信厂商口径。它同时给出去掉图表的
逐题结果、成本推导和灵敏度分析，可以直接拿 `results/v1.2/jevbench-v1.2-results.json`
按自己的权重重算。

**未收录**：`results/v1.1` 与 `results/v1.1.3` 的数据文件（历史版本，已被 v1.2 取代；
对应的说明文档 `RESULTS-v1.1*.md` 仍收录）、11 个上游模型适配器（只留基类与 4 种范式）、
CI 配置。README 中指向这些历史数据文件的 4 个链接会失效，属预期。

---

### 16 · Agent 工程实践长文 — `16-wechat-agent-engineering/`

腾讯技术工程的**万字工程实践**（约 1.6 万字），作者是高级前端开发 daryl。
标题即论点：《把 Agent 的「判断题」从大模型里拆出来》。

作者一开始是怀疑的——「一个不生成文本的模型能有多大空间？GPT 已经能做
structured output 和 tool calling」——读完 `fast-jev-compaction` 并自己仿写 Demo 后，
他给出的结论不是「Jev 更便宜」，而是一个更具体的工程判断：

> Agent 里很多模型调用不是为了生成答案，而是为了替代码做一次判断。

**这篇最值得读的是它和包内 `04` 的互补关系**。`04` 是源码本身，这篇是**逐层拆解**：
先讲清楚为什么需要「快判断层」（生成成本与判断需求不匹配、摘要破坏可复核性、
置信度没进入代码分支——三层论证），再进 `fast-jev-compaction` 的实现细节：

- **工具调用配对**：怎么把 `tool_use` 和 `tool_result` 绑定
- **state 构造**：怎么把「原始历史」变成「判断用状态」（附状态映射表）
- **`fitState` 逐级降级**：预算不够时不粗暴删消息，而是分阶段降级
- **两个 Noul 拆出三种压缩动作**：keep / truncate / drop 的判定逻辑
- **分批请求与失败回退**

10 张架构图（判断层数据流、摘要压缩 vs 决策剪枝对比、工程总览等）已本地化，
23 个代码块完整保留。

**看这篇是为了**：理解 Jev 在**上下文治理**这个具体问题上的完整工程闭环——
从问题定义到 state 设计到降级策略到失败处理，是一份可以直接参照的落地范式。

---

### 17 · 在硅基世界掷圣杯 — `17-wechat-silicon-grail/`

腾讯技术工程的**概念+实操混合长文**（约 1.4 万字），写作风格偏思辨，
用「掷圣杯」比喻 Noul 这种是非判断原语——工业系统每天上万次运转，
不需要洋洋洒洒的小作文，只需要在分岔路口迅速笃定地掷一次。

结构上覆盖：三大原语的定位（Noul = switch、Choice = switch-case、Score = 有序标尺）、
创始人背景、软件工程撞上的四堵「工程墙」、真实 HTTP 请求/响应示例（完整 JSON 保留）、
投机式并发（Speculative Fan-out）、**四类落地用法**（浏览器 Agent 动静解耦、
命令行安全刹车片、不看画面的马力欧/DOOM、链上高频做市）、成本性能账、
以及选型判据 **「The Boundedness Rule」**（有界性法则）。

其中**「神谕的短板」一节尤其值得看**——主动列出五条局限：
类型安全不等于事实正确、警惕静默失败、它绝对不是计算器、**给选项留一条逃生通道**
（枚举里要有「其他/不确定」选项）、语言环境的工程建议。

引用了几组实测数据（如 210 次命令对照中准确率 98.6%、中位延迟 312ms、
对比组 p95 6583ms），这些属作者所述，请对照原文判断。

**注意**：本目录与 `12`、`16` 均出自腾讯技术工程公众号，版权归其所有，包内为存档快照，请勿对外分发。

---

### 18 · Jev 能替代 Rerank 模型吗 — `18-wechat-rerank-experiment/`

Zilliz 的**对照实验报告**（约 4500 字），回答一个具体问题：用 Jev 做检索精排，
相比专用 reranker 到底如何？这是包内**唯一一篇带完整实验数据、且结论对 Jev 不完全有利**的材料。

**实验设计**：以 Milvus 为向量库，BEIR 的 SciFact 数据集（5,183 篇文档、300 条查询中固定种子抽 80 条），
三条路径共享同一份 shortlist（向量召回 + 词重叠召回，RRF 融合取 top-30），
只比较精排环节：不做精排 / qwen3.7-text-rerank / Jev。

**结论是双向的**：

| 维度 | 结果 |
|---|---|
| 效果 | Jev 的 nDCG@10 提升 **0.0778**，高于传统精排的 0.0446（**高 0.0332**） |
| 延迟 | Jev 精排 P50 **2075 ms**，约为传统精排（202 ms）的 **10.2 倍** |
| 成本 | 单次精排费用约为传统精排的 **6.7 倍**（$0.00227 vs $0.00034） |

所以作者的判断是：**离线检索、数据清洗这类不敏感于一两秒延迟的任务，Jev 优势突出；
在线场景里，仅精排就多出接近两秒，后面的生成模型还没开始工作，体验容易被拖慢。**

**阈值过滤那部分尤其值得看**——Jev 返回的是概率，能不能直接删掉低分文档？
实验用 0.5 阈值，top-5 precision 达到 49.4%，**但同时误删了 18.8% 的金标**。
作者的评论很关键：「对 RAG 来说，这个代价可能比多保留几条无关文档更严重，
因为被删掉的可能正是回答问题所需要的证据。」并且明确说明 0.5 不是默认答案，
阈值要按业务对「误删证据」的容忍度来调。

**文章还诚实标注了两处局限**：三种方案用的是同一份候选集（所以 Recall@K 都是 90%），
以及 qwen 用中位数阈值、Jev 用固定 0.5，两边过滤强度并不相同——这会影响过滤实验的可比性。

12 张图表（含延迟成本对比表、阈值过滤对比表）已本地化；末尾还推荐了几个 Jev 项目
（`fast-jev-compaction`、`jev-browser`、`jev-search`、`Reticle` 等）。

**注意**：版权归 Zilliz 所有，包内为存档快照，请勿对外分发。

---

## 一条主线怎么走

如果要把这些串起来理解，建议这个顺序：

1. **`10`** — 先用第三方报告建立全局认识：Jev 是什么、贵不贵、快多少、边界在哪
2. **`15`** — 再看独立评测的横向排名：它在你关心的任务上到底排第几，成本怎么算
3. **`18`** — 然后看一篇**具体任务的对照实验**：Jev 做精排赢在效果、输在延迟与成本
4. **`12`**、**`17`** — 再看从业者的务实解读，学会区分「说明了什么」与「不能说明什么」
5. **`14`** — 想快速上手就看这份讲座稿：从模型特性到 LangChain 集成 demo
6. **`01/concepts/system-one.md`** — 再校准到官方口径的心智模型：模型不做生成，做判断
7. **`01/primitives/`** — 三种问题原语的语义与提问方式
8. **`06/SKILL.md`** — 从「行为倒推判断」的设计方法论
9. **`04`** + **`16`** — 源码 + 万字拆解：`noul` 在上下文治理中的完整工程闭环
10. **`03`** — 看 `Choice` 在硬实时 + 资金约束下的用法与降级
11. **`07`** — 看动态候选集怎么把动作空间做成「随页面生长」
12. **`11`** — 看状态表示：同一款游戏，喂截图还是喂结构化对象
13. **`02`** — 想往下走到训练自己的决策模型时，读这个
14. **`08`** — 要在 agent 框架里做模型路由时读这个
15. **`09`** — 查实现细节
16. **`13`** — 最后看规划文档与资料清单，按图索骥继续深挖

---

## 关于这个包

- **Markdown 全量**：README、docs/、research/、categories/、cookbooks/ 等整目录收录
- **代码只取核心**：保留文件与上游**逐字节一致**，未作任何改写；仅调整了目录结构
  （各项目代码统一放入 `code/`；`15` 例外——它保持上游目录结构，因为它的文档大量
  按相对路径引用同仓库其他文件）
- `10`、`13`、`14` 由飞书云文档导出为 Markdown，内嵌表格已转为表格内联、公式与配图已本地化
- `12`、`16` ~ `18` 由网页 HTML 转换为 Markdown，正文配图已本地化，代码块保留原始格式；
  页眉渐变图与推广卡已丢弃
- 未收录的测试、脚手架、构建产物、数据集、模型权重等，请回各自上游仓库获取
- 各项目版权与许可归原作者所有，清单见 [`SOURCES.md`](SOURCES.md)
- `10`、`13`、`14` 出自飞书 wiki，`12`、`16`、`17` 出自腾讯技术工程公众号，
  `18` 出自 Zilliz 公众号，均为存档收录，**请勿对外分发**
