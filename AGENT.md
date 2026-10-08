# AGENT.md — jev-cookbook 项目工作流手册

> 给 AI 助手与新成员的任务手册：如何在本项目里**为新章节制作「理论 + 实验」中文笔记本**，
> 以及如何维护文档镜像站。本文件由「架构模式」章笔记本（`main/patterns_experiments.ipynb`）
> 的完整制作过程沉淀而来，照做即可复现同等质量。

## 项目是什么

- **Jev Cookbook 中文课程站**：首页介绍课程、十一章目录与学习路线；`course/01/` 至 `course/11/` 从 `main/` 各章 README 生成在线导读，Notebook 与工程通过仓库链接阅读和运行。
- **配套中文参考文档**：`introduction/` 为 docs.typesafe.ai 社区翻译的入口，`content/` 经 `build.py` 生成静态页面，保留原文档 URL 路径。
- **拓展阅读**：`materials/` 按主题挂载第十一章的全部知识库；首页和侧栏均有入口，子文档自动发现并进入搜索。板块元数据维护于 `site/reading.json`。
- **章节实验与项目材料**：`main/` 按十一章组织 Notebook、生成器、工程与知识库。实时 API、归档回放和人工离线示例的验证范围，以各章说明为准。

## 目录与关键文件

```
jev-cookbook/
├── content/            # 知识库：109 页中文翻译（与原站 URL 一一对应）← 笔记本的理论来源
├── build.py            # 站点生成器（python3 build.py 一键重建 + 自动校验内链）
├── dist/               # 构建产物（Pages 部署的就是它）
├── assets/             # 站点样式/脚本/图片
├── site/               # 课程首页模板、章节元数据与站点维护说明
├── anchor_maps.json    # 跨页锚点「原文↔译文」映射（构建数据）
├── _orig/              # 英文原稿存档（本地有、gitignore 不入库）
├── apps/               # DSH × Jev 配套工程（main/09_Agent集成 的实体）
└── main/
    ├── patterns_experiments.ipynb     # 已完成的范例：架构模式实验 ← 新章节照这个标准做
    ├── cookbooks/                     # 官方 18 篇实战指南，一篇一个笔记本
    ├── generators/                    # 生成器脚本目录 ← 新章节照 build_patterns_notebook.py 写
    │   └── build_patterns_notebook.py
    ├── pi_jev_demo/                   # Pi + Jev 配套 extension 与 skills
    ├── setup_env.sh                   # 一键环境（Python ≥3.10 + 全部依赖，优先 uv）
    ├── requirements.txt
    └── README.md
```

## 铁律（先读，违反必返工）

1. **API Key 只从环境变量 `TYPESAFE_API_KEY` 读取**。任何文件不得硬编码 Key；
   每次提交前全树扫描：`grep -rl "<key指纹片段>" . --exclude-dir=.venv --exclude-dir=_orig --exclude-dir=.git`
2. **语言约定**：产品名（TypeSafe/Jev/Choice/Score/Noul/System One/Playground）、选项 key
   （`billing`、`check_balance`…）、字段名（`instructions`、`confidence`…）保持英文；
   state、instructions、criteria 的**描述文字**、所有解说一律中文。
3. **笔记本必须走「生成器脚本 → 生成 → 执行」三段式**，不要直接手改 `.ipynb`。
   结构模板照抄 `build_patterns_notebook.py`。
4. 官方 SDK 要求 **Python ≥ 3.10**（macOS 系统自带 3.9 装不上）。环境用
   `cd notebooks && ./setup_env.sh`，之后所有 python/jupyter 命令走 `.venv/bin/`。
5. **子代理并发每波 ≤ 3 个**（账户级限流 1302；翻译/批量抓取时按波次派发）。

---

## 工作流 A（核心）：为某章节制作实验笔记本

### A0 选章并研读知识库

- 知识库就在 `content/`（构建后 `dist/` 里是渲染好的 HTML，读 Markdown 源更方便）。
- 先读**目标章节**，再读概念章作理论底座：
  `concepts/system-one.md`、`concepts/state.md`、`primitives.md`、`confidence.md`、
  `concepts/how-to-build-with-system-one.md`。
- 技巧：Mintlify 导出的 md 里有内嵌的 `export function Xxx(...)` 组件定义块，
  用下面命令剥掉再读正文：
  ```bash
  awk '/^export function/{skip=1} skip && /^}$/{skip=0; next} !skip{print}' content/<章节>.md
  ```

### A1 提炼理论 → 写成「📖 理论」块

- 每章开头放 **📖 理论根基**（若概念尚未介绍，先放一整节 **📖 理论速览**）。
- 要求：**中文重述、提炼要点，不整段照抄**；标注出处链接（原文 + 中文镜像站对应页）。
- 必须覆盖的概念（按章节取舍）：校准（calibration）在成组预测上度量、不保证单次正确；
  「一秒判断」原则；所有问题共享同一 state、独立评估、按 ID 返回；ID 不发送给模型；
  `score` 是概率加权期望值（`0×0.0+1×0.57+2×0.43=1.43` 官方算例）；Noul 没有 confidence；
  confidence 是 probabilities 分布形状的压缩；低置信度在 Choice/Score 上分别意味着什么；
  「我不知道」是有用信号；三种软件架构与"代码掌控制权"。

### A2 设计实验（先探针，后定稿）

- **忠实复刻文档示例并中文化**：文档里每个模式/功能用什么例子，笔记本就用对应中文场景。
- 实验要**覆盖文档声称的行为路径**：门控的每条分支、扇出的"投机忽略"、权重的排名反转……
- **探针校准是关键步骤**：模型的真实置信度分布未必落在文档假设的区间。先用 curl 直连
  `POST https://api.typesafe.ai/v1/systemone`（`Authorization: Bearer $TYPESAFE_API_KEY`）
  批量试措辞，找到能真正触发各分支的输入（例：实测发现 0.6–0.85 置信区间几乎不会命中，
  而「行，就按你说的办」能稳定触发 <0.6 兜底）。**把这类实测发现写进理论块**——这是本
  系列笔记本最有价值的部分。
- 已知行为事实（写实验时直接用）：`noul` 无 confidence 字段；`score` 是期望值可为小数；
  中文提示词模型同样处理良好；乱输入（如「。。。」）置信度会掉到 0.3 以下。

### A3 写生成器 `main/generators/build_<章节>_notebook.py`

结构模板（照抄 patterns 版，逐段替换内容）：

```
封面 md        # 结构表、运行要求、setup_env.sh 用法、Key 安全提示、语言约定
0. 准备        # 0.1 %pip 安装 → 0.2 导入与客户端 → 0.3 连通性测试
               # 0.4-0.5 离线回退替身类与 TS 助手（原样保留）→ 0.6 本章离线示例数据
📖 理论速览    # 概念章提炼（首章笔记本才需要完整版，后续章节可精简）
每模式/每主题： # 原理 md → 📖 理论根基 md → 步骤 md → 小代码格 → 输出 → 观察要点 md
小结 md        # 行为对照表 + 延伸阅读 + 离线模式提醒
```

单元格粒度标准（来自 review 反馈，必须遵守）：

- **一个单元格只做一件事**：定义数据、定义问题、调用、打印结果各自成格；
- 节奏固定：**原理 → 理论根基 → 步骤说明 → 小段代码 → 输出 → 观察要点**；
- 说明与代码单元格数量比约 3:2；每段代码不超过 ~30 行；
- 数据常量用大写（`TICKET`、`BANK_QUESTIONS`）；离线示例数据集中在 0.6 节，不混进实验格；
- ⚠️ 生成器里中文双引号字符串**不要内嵌 ASCII `"`**，用中文引号“”；写完先 `py_compile`。

### A4 生成并执行

```bash
cd notebooks
.venv/bin/python generators/build_<章节>_notebook.py   # 生成 ipynb（输出到 main/，可从任意目录运行）
TYPESAFE_API_KEY=$TYPESAFE_API_KEY .venv/bin/python - <<'EOF'
import nbformat
from nbclient import NotebookClient
nb = nbformat.read("<章节>_experiments.ipynb", as_version=4)
NotebookClient(nb, timeout=180, kernel_name="python3", allow_errors=False).execute()
nbformat.write(nb, "<章节>_experiments.ipynb")
errs = [o for c in nb.cells if c.cell_type=="code" for o in c.outputs if o.output_type=="error"]
print("错误:", len(errs))
EOF
```

- `allow_errors=False`：任何单元格异常即失败，当场修；
- 执行完**逐格阅读输出**：确认每条行为路径都被真实输出触发、结论与理论块一致；
- Key 无效时会自动落入「离线示例模式」（TS 助手的 401 回退），流程仍可跑通，
  但交付前必须换有效 Key 重跑，确保**零离线残留**（grep 输出里不应再有「离线示例」）。

### A5 质量门（全部通过才算完成）

1. 生成器 `py_compile` 通过；notebook `nbformat.validate` 通过；执行零错误；
2. 无「离线示例」残留输出；无 Key 泄漏（铁律 1 的 grep）；
3. 中文规范：解说全中文、标识符英文、无 ASCII 引号嵌套问题；
4. 单元格粒度与说明密度达到 A3 标准；
5. 更新 `main/README.md` 的笔记本列表。

### A6 提交与发布

```bash
git add -A && git commit -m "新增《<章节>》中文实战笔记本" && git push
```

Pages 工作流会执行 `python build.py --check`，然后部署 `dist/`。修改站点模板、课程元数据、
章节 README、`content/` 或已挂载的 Notebook 后，先在本地运行 `python3 build.py --check`，
确认内链/资源校验通过并检查构建差异，再推送。详细说明见 `site/README.md`。

---

## 工作流 B：维护文档镜像站（原站更新时）

1. 重新抓取变更页：Mintlify 站点支持 `https://docs.typesafe.ai/<路径>.md` 直接拿 Markdown；
2. 按仓库 README「翻译约定」翻译（术语表在那里），替换 `content/` 对应文件；
3. 跨页锚点映射会随 `python3 build.py` 自动重建（写入 `anchor_maps.json`）；
4. `python3 build.py` 输出末尾的校验必须全绿（内链/资源/锚点）；
5. 翻译若用子代理：**每波 ≤3 个同步调用**，单批 ≤80KB，波间自然间隔。

---

## 已知坑（全部踩过，别再踩）

| 坑 | 解法 |
|---|---|
| macOS 系统 python3 是 3.9，SDK 装不上 | 用 `main/setup_env.sh`（uv 自动下 3.12） |
| uv 创建的 venv 不带 pip，笔记本 `%pip` 报错 | setup_env.sh 已补装 pip；新环境记得验证 |
| bash 变量名后紧跟全角括号会解析进变量名 | 一律写 `${VENV}` |
| 生成器中文串内嵌 ASCII 引号 → SyntaxError | 用中文引号“”；提交前 py_compile |
| 0.6–0.85 置信区间实测几乎不命中 | 先探针校准措辞，把实测发现写进理论块 |
| Mintlify md 导出含 MDX 组件定义噪音 | awk 剥离 `export function` 块再读 |
| `score` 直接加权会量纲错配 | 先除以最高档归一化到 0–1 |
| 20 路并发子代理触发账户限流 1302 | 每波 ≤3 个同步调用 |

---

## 章节候选清单（按此顺序做即可）

| 章节 | 笔记本实验创意 | 重点理论块 | 状态 |
|---|---|---|---|
| 架构模式 patterns | 推测性扇出 / 置信度门控路由 / 复合评分 / 意图路由 | 三种软件架构 | ✅ 已完成 |
| 原语 primitives | 同一个中文 state 分别用 Choice/Score/Noul 提问，对比三种答案形状；`other` 选项的作用 | 一秒判断原则、问题解剖 | ✅ 已完成 |
| 置信度 confidence | 同一问题的 probabilities 形状 vs confidence 的关系；构造高/中/低置信输入 | 分布形状、三路径 | ✅ 已完成 |
| 实战指南 cookbooks | 官方 18 篇逐篇一个笔记本（前 8 篇由 `build_cookbook_notebooks.py` 统一生成） | 按篇章 | ✅ 18/18 已完成 |
| 状态 state | 字符串 vs 结构化对象 state 的效果对比；「只给所需上下文」 | 状态格式表 | 已合入，离线验证通过，真实 API 待验收 |
| 快速开始 quickstart | 跟着官方 Playground 流程走一遍 API 最小实验 | 请求模型 | 已合入，离线验证通过，真实 API 待验收 |
| 简介 introduction | 多维判断与加权组合 | 判断与程序控制 | 已合入，离线验证通过，真实 API 待验收 |
| AI 入门 ai_primer | 明确、否定与模糊表达的概率对照 | 概率信号与校准边界 | 已合入，离线验证通过，真实 API 待验收 |
| System One system_one | 退款三问、组合路径、问题 ID 对照 | 共享 state 与独立判断 | 已合入，离线验证通过，真实 API 待验收 |
| 如何构建 build_with_typesafe | 客服分支与五个小配方 | 代码掌握控制权 | 已合入，离线验证通过，真实 API 待验收 |
| 应用场景地图 use_case_map | 相关性排序与空结果出口 | 可验证配方与效果边界 | 已合入，离线验证通过，真实 API 待验收 |
| 模型 models | 各模型别名与行为差异（如可得） | 校准概念 | ⬜ 待做 |

做完一章后：更新本清单状态、`main/README.md`、推送。

入门与概念七章通过 `main/generators/build_foundations_notebooks.py` 批量生成，维护与验收说明见
[`main/MAINTENANCE.md`](main/MAINTENANCE.md)。`main/validation/offline_previews/` 为人工输出，
不能作为 A5 的真实 API 验收依据；本组默认 `live` 失败即停止，不自动回退。

> 另有与文档章节无关的内容：`apps/`（DSH 决策协作工程，可运行）；Laya 相关已并入 `main/10_本地模型/`
> （开源 System 1 决策模型 Laya 的介绍与本地调用），都不走笔记本三段式。

DSH × Jev 学习案例的工程在 `apps/dsh-jev-decision/`，配套 Notebook 由
`main/generators/build_dsh_jev_decision_notebook.py` 生成。该本默认实时调用，显式 recorded
模式只分析真实归档证据，不是人工离线数据，也不能宣称本次实时验收通过。运行方式与待办见工程案例说明。
