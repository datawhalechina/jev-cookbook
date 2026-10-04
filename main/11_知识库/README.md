# 第十一章 · 知识库

> 这是教程的证据索引：用来找到数字、代码和观点从哪里来，收录时使用了哪个版本，以及哪些许可和限制需要保留。

## 快照范围

本章含从上游 jev-cookbook 导出的 21 个资料板块和 Laya 示例，另收录 7 篇外部文章（23 Clef 决策模型，Cloudflare Blog；24 Jev 工程实战，@polydao；25 Gero-4B RL 训练平台，@TheVixhal；26 Jev 评审实战，@akshay_pachaar；27 本地自制 Jev，@_avichawla；28 pg-jev 上手，「AI工程化」；29 StartLux 决策模型报道，机器之心）。目录重排和收录范围见[来源清单](jev-cookbook/SOURCES.md)，该清单记录了 2026-09-23 打包时各上游 commit、文件数量、未收录内容和许可。快照日期不代表资料仍是上游最新版本。

```mermaid
flowchart LR
  C[教程中的结论或数字] --> S[来源文件与原始链接]
  S --> V[版本、commit 与日期]
  V --> R[记录数据、模型、基线和指标]
  R --> B[注明证据类型与适用边界]
  B --> L[核对许可与传播限制]
  L --> U[需要更新时保留旧版并记差异]
```

查数字时可按证据链倒着走：先找到 README 中的结论，再核对来源文件 / 论文版本、数据切分、运行配置与原始结果。官方接口文档能支持“接口这样定义”，论文能支持“作者在该设置下报告了结果”，本地日志能支持“本仓库这次运行观察到结果”；三者不能互相替代。若缺少原始数据、标签或运行条件，应把说法降为案例观察或待验证假设。

### 把一个实验数字记成可追溯的记录

```yaml
claim: "这里写希望引用的结论，不把它改写成更强的主张"
source: "论文 / 上游页面 / 本地报告路径"
version_or_commit: "tag、commit、论文版本"
dataset_and_split: "数据集、样本数、切分、是否有人审标签"
model_and_run: "模型、参数、日期、硬件、重试与成本口径"
metric_and_baseline: "指标定义、对照组、区间或重复次数"
evidence_type: "接口文档 / 作者报告 / 本仓库实测 / 离线示例"
limitations: "哪些范围尚不能从这条记录推出"
license: "代码、数据或文章的再使用条件"
```

任何一个字段缺失，都应限制对应结论的强度：例如只保存了 Notebook 输出截图、没有原始数据和运行配置，就不宜称为“可复现基准”。

## 按用途查找

| 资料 | 可查内容 | 阅读时注意 |
|---|---|---|
| [官方文档中译](jev-cookbook/01-official-docs-zh/) | System One、state、原语和官方配方的中文材料 | 非官方社区翻译；接口变动时核对官方文档 |
| [NanoJev](jev-cookbook/02-nanojev/) | 小型应用的确定性引擎与判断接口模式 | 示例不等于生产级模型基准 |
| [JevBench](jev-cookbook/15-jevbench/) | v1.2 系列冻结题集、计分方法和结果 | 比较前确认 v1.2.3 的计分、价格和延迟调整 |
| [Rerank 研究文章](jev-cookbook/18-wechat-rerank-experiment/article.md) | 80 条 SciFact 上的重排序对照 | 单一数据集、候选集与基线上的报告 |
| [Fast Jev Compaction](jev-cookbook/04-fast-jev-compaction/) | Claude Code 上下文压缩示例 | 上游版本与许可见 SOURCES |
| [Eve 与研究报告](jev-cookbook/08-eve-decision-models/) | 决策模型横向讨论 | 区分二手分析与原始实验 |
| [Clef 发布文译文](jev-cookbook/23-clef-decision-models/article.md) | Cloudflare 决策模型 Clef 的完整评测数字（Jev Decision Index、延迟表）与 RL 微调服务介绍 | 厂商自报数据；对照 [JevBench](jev-cookbook/15-jevbench/) 的独立复测再引用 |
| [Jev 工程实战译文](jev-cookbook/24-polydao-jev-engineering/article.md) | 把智能体里的小决策迁到 Jev 的完整方法：四桶分拣、问题写法、置信度路由、Kimi K3 兜底与成本账 | 个人从业者实战总结；数字为作者自报口径，无样本细节处按案例看待 |
| [Gero-4B 训练平台译文](jev-cookbook/25-vixhal-gero-rl/article.md) | 用 MLX 在 MacBook 上把 Qwen3-4B 训成 Jev 式决策模型的完整代码路径：奖励塑形、校准分组、结果复现 | 个人复现教程；结果为作者单机自报，未见第三方复测 |
| [Jev 评审实战译文](jev-cookbook/26-akshay-jev-judge/article.md) | 用 Jev 替代 LLM-as-judge 评估智能体：依据性/行动核实等有界判断、与 Opik 集成的完整代码 | 实操教程；示例数据与结论为作者自报，规模与基线未附 |
| [本地自制 Jev 译文](jev-cookbook/27-avichawla-diy-jev/article.md) | 不重训练、用 next-token 打分把开源 LLM 变成本地决策引擎：受约束选项、概率分布、SGLang 部署与延迟实测 | 教育博主教程；benchmark 为作者单机自报口径 |
| [pg-jev 上手](jev-cookbook/28-pg-jev/article.md) · [项目 README 中译](jev-cookbook/28-pg-jev/README.md) | 把 Jev 包装成 SQL 函数的 PostgreSQL 扩展：自然语言 WHERE/排序/分类，含性能实测与四条部署注意 | 中文原创上手文 + README 非官方中译；实测数字为公众号作者自报口径 |
| [StartLux 决策模型报道](jev-cookbook/29-wechat-startlux-decision/article.md) | 中国开源决策模型 StartLux-Decision 在 Decision Index 0.2.1 登顶：五档参数、基准数字、架构与本地部署路线 | 媒体报道；评测数字来自厂商/榜单口径，引用前回 Decision Index 与模型卡复核 |
| Laya 资料 | [架构](jev-cookbook/19-wechat-laya-architecture/article.md)、[开源发布](jev-cookbook/20-wechat-laya-oss-release/article.md)、[榜单报道](jev-cookbook/21-wechat-laya-hf-trending/article.md)、[本地接口](jev-cookbook/laya-model/README.md) | 参数、排行榜和下载信息都要回到当前模型卡复核 |
| 其他板块 | trader、技能、SDK、飞书研究与公众号文章 | 私有文档或受版权保护的内容不能因被收录就自由再分发 |

## 给实验结论标注证据

引用数字时，至少写清：

- **出处与版本**：上游链接、commit 或 benchmark tag。
- **时间与范围**：运行日期、数据集、样本数量和切分。
- **运行条件**：模型版本、参数、端点、机器、并发、成本口径。
- **证据类型**：接口文档、可复现测量、离线演示、研究论文或二手报道。
- **适用边界**：基线、置信区间、选择偏差、隐私与许可限制。

例如，JevBench 的榜单结论应链接到固定的 v1.2.3 结果，而不是只引用网页上会继续更新的排名；重排序数字要同时标明 SciFact 和候选集。没有样本和标注支持的观察，应称为案例或假设，不能写成普遍性能。

## 使用与更新

查目录来源、commit、未收录范围和许可证，先看 [SOURCES.md](jev-cookbook/SOURCES.md)。引用或再分发公众号、飞书文档、上游未附许可的代码前，遵守来源清单中的限制。私有 wiki 的快照尤其不能因保存在仓库里而对外传播。

更新快照时保留旧版本可追溯性，并记录新的来源、commit、日期、差异与许可变化；对教程中受影响的数字同步更新对应章节说明。模型权重和数据集未随此知识库完整收录，按各自来源页面申请或下载。
