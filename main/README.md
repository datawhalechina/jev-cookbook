# Jev 决策模型教程（十一章）

这里按「证据 → 问题 → 概率 → 策略 → 动作 → 评估」介绍如何把类型化判断接入软件。每章都链接到实际 Notebook、工程或资料；是否调用真实 API、使用什么数据，以对应页面的运行说明为准。

Jev 的公开接口适合答案空间有限、需要结构化概率输出的判断任务。它不取代需要开放式生成、长链推理或创作的 LLM。教程按公开接口解释行为，不推断服务端未公开的内部实现；API 实测、离线演示与外部榜单也分开说明。


## 建议阅读路线

- **第一次接触**：第 1 章认识 Jev → 第 2 章核心概念 → 第 3 章架构模式。
- **想动手做应用**：第 4 章 Cookbook → 第 5 章智能家居 → 第 7 章项目案例。
- **关注 Agent 工具安全**：第 2 章置信度 → 第 3 章门控 → 第 9 章 Agent 集成。
- **想比较或训练模型**：第 6 章评测 → 第 10 章 Laya 本地模型。
- **查证社区资料**：第 11 章知识库；第 8 章用于阅读前沿研究。

## 章节地图

| 章 | 学完后能做什么 | 入口与材料 |
|---|---|---|
| 1 · 认识 Jev | 说清有限选项判断和自由文本生成的差异；完成一次多问题调用与代码分流 | [入门 Notebook](01_认识Jev/01_认识Jev.ipynb) · [章节说明](01_认识Jev/README.md) |
| 2 · 核心概念 | 设计 state、选择 Noul / Choice / Score（外加野区的图像与 box），并区分概率、置信度、正确率和校准 | [从 System One 开始](02_核心概念/01_SystemOne.ipynb) · [七册路线](02_核心概念/README.md) |
| 3 · 架构模式 | 将扇出、置信度门控、复合评分和意图路由组合进应用 | [架构模式 Notebook](03_架构模式/01_架构模式.ipynb) · [章节说明](03_架构模式/README.md) |
| 4 · 实战指南 | 按检索、风险控制、可靠性或结构化处理选择 18 个 Cookbook | [18 篇目录](04_实战指南/README.md) · [Notebook 文件夹](04_实战指南/) |
| 5 · 智能家居 | 观察模型判断、确定性控制流和 3D 模拟动作如何协作 | [Notebook](05_智能家居实验/01_智能家居实验.ipynb) · [本地演示](05_智能家居实验/smart_home_demo/) |
| 6 · 模型评测 | 固定数据和运行条件，比较准确率、概率质量、速度、成本与覆盖率 | [评测 Notebook](06_模型评测/01_模型评测.ipynb) · [基准工具](06_模型评测/benchmark/) · [通用评测框架](06_模型评测/llm_eval/) |
| 7 · 实战应用 | 从游戏和应用代码中辨认 state、判断、动作和反馈的边界 | [项目地图](07_实战应用/README.md) · [应用代码](07_实战应用/app/) |
| 8 · 前沿研究 | 用问题、基线、数据、指标和限制阅读 Jev-Mem、Agent 级联及领域研究 | [研究地图](08_前沿研究/README.md) · [Jev-Mem Notebook](08_前沿研究/jev_mem/jev_mem_walkthrough.ipynb) |
| 9 · Agent 集成 | 在工具执行前加入语义判断，同时让代码保留权限与动作控制 | [章节说明与实验](09_Agent集成/README.md) · [Pi Notebook](09_Agent集成/01_Pi集成实验.ipynb) · [DSH Notebook](09_Agent集成/02_DSH决策协作.ipynb) |
| 10 · 本地模型 | 了解 Laya、构造决策数据、比较 SFT / LoRA / RLCD 并部署评测 | [章节说明](10_本地模型/README.md) · [数据与训练文档](10_本地模型/FINETUNING.md) |
| 11 · 知识库 | 查找教程数字、社区项目的出处、版本和许可 | [资料索引](11_知识库/README.md) · [快照来源清单](11_知识库/jev-cookbook/SOURCES.md) |

## 运行 Notebook

不使用远程 TypeSafe API key 时，先运行 [LocalJev.ipynb](LocalJev/LocalJev.ipynb) 到“发布连接配置”。它自动检查并补齐模型文件、优先选择可用 GPU、启动本机服务。当前提供 Laya 服务，默认是小型多语言 Laya；Liquid D1、LLaMA／LFM 暂只列硬件参考，适配服务不随本分支提交。模型、硬件参考和可填写的硬件评估 Prompt 见 [本地模型说明](LocalJev/LocalJev.md)。第 1～4 章的 25 本 SDK Notebook 会读取本地连接配置，第 5 章智能家居 Notebook 会将连接交给其网页服务；本地服务未就绪会明确报错。语音与生成式聊天等独立服务仍按各章要求配置。

本次最小验证范围是 Windows 上的默认多语言 Laya；macOS/Linux 和其他模型尚未完成本次验收，原有功能继续保留。首次克隆后，从仓库根目录执行以下 Windows 初始化命令：

Windows PowerShell：

```powershell
cd main
powershell -NoProfile -ExecutionPolicy Bypass -File .\setup_env.ps1
.\.venv\Scripts\python.exe -m jupyterlab LocalJev/LocalJev.ipynb
```

Windows 脚本创建项目自己的 `.venv`，安装 Jupyter、SDK 和默认 Laya 服务依赖，并注册 `Python (jevbook)` 内核；不依赖个人 Conda 环境。建议先安装 [uv](https://docs.astral.sh/uv/getting-started/installation/)，脚本会自动准备 Python 3.12 并通过 `--torch-backend auto` 匹配 PyTorch 构建；没有 uv 时需已安装 Python 3.10–3.12，pip 分支使用平台默认构建。CUDA 需要受支持的 NVIDIA 显卡和驱动；初始化末尾打印能否使用 CUDA，Windows 运行时优先 CUDA，再选 CPU。只需要 CPU 时可传 `-TorchBackend cpu`。macOS/Linux 的原有 SDK 环境仍可通过 `bash setup_env.sh` 初始化；本次不将它作为本地模型验收路径。

首次安装会下载运行依赖，首次 Run All 会下载默认模型（约 0.7 GB，加上缓存和框架需更多磁盘空间），都需要联网。默认模型建议至少有 4 GiB 空闲内存，GPU 路径建议 2 GiB 空闲显存；见 LocalJev 的估算说明。权重位于 `main/.models/`，连接文件 `.local-jev.json` 和模型都不会进入 Git。已有环境可直接用它的 Python 安装 `LocalJev/requirements-local.txt` 后重新启动 Jupyter；D1 / 新版 LFM 的依赖另见 LocalJev。

每次使用顺序：

1. 在 `LocalJev/LocalJev.ipynb` 使用项目的 `Python (jevbook)` 内核，执行 **Run All Cells**，看到真实预测结果和“服务保持运行”。保留默认 `STOP_SERVICE=False`。已有正常运行的个人环境也可继续使用其内核。
2. 保持 LocalJev 的服务及其内核运行，在本仓库打开第 1～5 章现有 Notebook，使用项目内核，直接执行 **Run All Cells**。若此前已执行过准备格，重新 Run All；不需要复制环境变量或填远程 TypeSafe key。
3. 开头出现“本次调用本地模型：…｜http://127.0.0.1:8001”即表明连接了本机服务。SDK 已安装时复用现有环境，不强制升级。若手动设置过 `JEV_RUN_MODE=offline`，先取消这个强制离线设置。
4. 全部实验结束后，回到 LocalJev 将 `STOP_SERVICE` 改成 `True`，运行停止格。关闭或重启 LocalJev 内核、重启电脑后，先重新运行 LocalJev，再运行其他 Notebook。

连接过程是：LocalJev 写本机 `.local-jev.json` → 第 1～4 章的准备格在各自内核中验证服务并设置 SDK 环境变量；第 5 章的准备格把同一连接交给网页服务 → 后续 TypeSafe 调用走本机 HTTP 服务。不同内核不会直接共享环境变量。SDK 的使用方式与远程 key 模式相同，预测来自当前本地模型；答案、概率、置信度和耗时可能与远程 Jev 不同。

当前已知边界：停止 LocalJev 不会清理其他内核已保存的连接，请重启相关内核；`auto` 下无凭据时使用离线教学替身。重新运行会更新“本次执行记录”的单元格输出，`live` 也包含本地真实请求。第五章部分卧室灯和咖啡机关闭指令的响应不符合用户预期，尚未定位；执行无报错不代表动作判断正确。

选择远程 TypeSafe 服务时，需移走本机 `.local-jev.json` 并重启其他 Notebook 的内核，再把远程 `TYPESAFE_API_KEY` 放在启动 Jupyter 的进程环境中。远程密钥不要写入 Notebook、配置文件或日志。远程调用可能计费，并受服务端版本、网络和限额影响；本地模式不需要该密钥。

离线运行使用 Notebook 提供的示例响应，例如：

    JEV_RUN_MODE=offline .venv/bin/jupyter lab 01_认识Jev/01_认识Jev.ipynb

离线数据用于理解结构和控制流，不是模型预测、性能或校准证据。部分旧 Notebook 有各自的运行模式；运行前先看该 Notebook 的「运行要求」。带外部语音或模型服务的演示还有独立配置要求，详见章节说明。

## 如何读实验结果

- **公开接口事实**：返回字段、输入格式和参数以对应版本的官方文档为准。
- **仓库实验快照**：记录数据、模型、环境和执行日期；只说明该次样本与设置。
- **外部榜单或社区结果**：固定引用数据集与版本，不把排名或价格写成稳定规律。
- **离线演示**：用来演示程序路径，不能与真实 API 结果混用。

教程中如果没有实验数据、标注或对照组，就把结论当作假设或设计建议；不能从一次正确输出推断准确率，也不能从高置信度推断正确。

运行记录、依赖约束与维护方法见[维护与验证说明](MAINTENANCE.md)。正式章节 Notebook 的目录与映射也在本 README 的章节地图中；仓库根目录的 [README](../README.md) 是项目总览。

## DSH × Jev 配套实验

[DSH 决策协作 Notebook](09_Agent集成/02_DSH决策协作.ipynb)可用已归档的真实响应复盘决策，不发送新请求。实时模式最多发出 4 次 TypeSafe 请求；设置 DSH_JEV_RUN_MODE=recorded 可重放归档数据。完整 DSH 工程还需按[工程说明](../apps/dsh-jev-decision/README.md)安装 Node.js 24 依赖并编译。Notebook 回放、实时 API 和完整工程会话是不同验证范围，阅读结果时不要混为一谈。
