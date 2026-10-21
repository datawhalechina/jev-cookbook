# DSH × Jev 决策插件

一个可复现的工程学习案例：让 **DeepSeek Harness 调用 Jev / TypeSafe 做结构化判断**，并提供可在 DSH 中选择的“Jev 决策协作”模式。

例如，用户提出“修复日期解析函数对空字符串的处理”，Agent 可调用 `jev_route_task`，获得任务类别、目标是否需要澄清、复杂度和下一步建议，再继续完成原任务。

本案例提供可安装的插件、演示模式、测试和中文说明。真实联调步骤与完整聊天练习见[最小验收指南](docs/ACCEPTANCE.md)。业务评测集、阈值校准和生产部署属于后续扩展。

**0.1.2 实测进展（2026-09-24）：** Jev 真实原语和分流检查通过；DSH 核心会话完成实际修复及提问后继续修复。已补强首步分流和澄清等待规则；网络失败与未覆盖项见[真实联调记录](docs/LIVE-VALIDATION-20260924.md)。

## 学习入口

- [案例讲解与未完成事项](docs/LEARNING-CASE.md)：设计、失败复盘和复现清单。
- [中文 Notebook](../../notebooks/dsh_jev_decision_experiments.ipynb)：原语、路由代码、会话证据与边界练习。
- [公开实验记录](validation/README.md)：真实响应摘录及两份修复后的练习文件。

仓库路径为 `apps/dsh-jev-decision/`，以下命令均从该目录执行。`dist/` 由 `npm run build` 生成，不入 Git；npm 安装包包含编译结果。

## 交付内容

| 内容 | 用途 |
| --- | --- |
| `jev_decide` 工具 | 一次请求中回答多个独立的 Choice / Score / Noul 问题 |
| `jev_route_task` 工具 | 任务分流演示：`proceed` / `clarify` / `review` |
| Jev 决策协作模式 | 在新任务开始时引导 DSH 使用分流工具 |
| 离线演示、自动化测试 | 没有 API Key 也能验证安装与代码路径 |
| TypeScript 源码、预编译 npm 包 | 可修改、可安装、可交付 |

**兼容基线：DSH `0.1.5-rc.2`，Cordis `4.0.2`。** 开发和验收使用 Node.js 24。DSH 主分支的预设接口已有变化，本项目不宣称兼容 `0.1.7-alpha`。请先按锁文件运行，再考虑升级。

`package.json` 的 `overrides` 同时固定锁文件中的 Cordis HMR `1.0.17` 和 timer `1.1.4`，避免 npm 重新解析 DSH 依赖树时选择锁文件之外的新插件版本，导致普通 `npm ci` 拒绝现有锁文件。安装无需启用 `legacy-peer-deps`。

## 1. 先运行不需要密钥的演示

安装 Node.js 24 和 pnpm，在本项目目录执行：

```bash
node --version
npm ci --ignore-scripts
npm test
npm run demo
```

`npm run demo` 使用真实的 DSH `ToolRuntime`，由脚本直接发起工具调用。它没有启动聊天主模型，也不访问 TypeSafe。演示用人工预设结果覆盖三条路径：

| 输入 | 演示输出 |
| --- | --- |
| 请修复仓库中日期解析函数对空字符串的处理，并补一个回归测试。 | `proceed`：开始处理 |
| 帮我把那个东西弄好。 | `clarify`：核心目标需要澄清 |
| 看看这份材料，代码和文案方面都处理一下。 | `review`：先检查上下文 |

每条结果包含 `source: "mock_fixture"`、`request_attempted: false`。它们是安装和逻辑演示，不能用于证明 Jev 的实际准确率。其他输入会获得均匀分布等中性夹具，不模拟语言理解。

## 2. 安装到 DSH 并添加模式

以下命令使用本项目锁定版本的 DSH，在项目内建立独立测试环境。**同一终端按顺序运行**，不需要全局安装 DSH：

```bash
# 从本项目根目录执行；Node.js 24 与 pnpm 须在 PATH 中。
npm run build
npm pack
export DSH_HOME="$PWD/.dsh-local"

# 创建一个基于 web 的独立 profile，打印配置后退出。
npx --no-install dsh --profile jev-demo --from-default-profile web --dump-config

# 安装预编译插件包：DSH 自动把 bundle patch 加入 profile。
npx --no-install dsh plugin --profile jev-demo add ./dsh-jev-decision-0.1.2.tgz --ignore-scripts

# 安装可选择的 Jev 模式；已有同名目录时拒绝覆盖。
node scripts/install-preset.mjs --home "$DSH_HOME"

# 检查合成配置，应包含 name: dsh-jev-decision。
npx --no-install dsh --profile jev-demo --dump-config
```

然后，按 [DSH 官方说明](https://github.com/deepseek-ai/deepseek-harness)配置主模型连接，在同一终端启动：

```bash
export DEEPSEEK_API_KEY='填入你自己的 DeepSeek Key'
export JEV_DECISION_MODE=mock
npx --no-install dsh --profile jev-demo
```

打开 DSH 打印的本地地址，在**新会话**的模式选择器中选择“Jev 决策协作”，输入上面的演示任务。让 Agent 调用 `jev_route_task` 并解释结果。`mock` 只关闭 Jev 网络调用；DSH 聊天主模型仍使用自己的连接和额度。

模式目录为 `$DSH_HOME/.agent-presets/jev-decision`，profile 目录为 `$DSH_HOME/profiles/jev-demo`。DSH 的模式目录在同一 home 内共享；需要使用该模式的 profile 都应安装本插件，否则它可能被 DSH 标记为不可用。

若要安装到已经使用的 DSH，请确认版本为 `0.1.5-rc.2`，使用其原有 `DSH_HOME` 和 profile 名替换上面命令。不设置 `DSH_HOME` 时，默认目录是 `~/.dsh`。

## 3. 切换真实 Jev 判断

TypeSafe Key 和 DeepSeek Key 来自不同服务，不能互相替代。先在终端设置自己的 TypeSafe 凭据，再单独验证 Jev：

```bash
export TYPESAFE_API_KEY='填入你自己的 TypeSafe Key'
export TYPESAFE_DEFAULT_MODEL=jev-1.13.0
export JEV_DECISION_MODE=live
npm run check:live
```

此命令通过 DSH 工具运行时，向 TypeSafe 发起**一次包含三种原语的真实请求**，会使用账户额度。报告中的 `results[].result` 保留实际模型、答案、token 用量、耗时与请求 ID；错误时退出码非零。脚本读取当前进程环境，不自动读取 `.env`。

再检查任务分流工具，最多发起 3 次真实请求：

```bash
npm run check:routes -- --output reports/live-routes-01.json
```

遇到第一个接口或工具错误就停止，不重试。报告不覆盖已有文件。三个案例的教学预期只用于比较，不发送给 Jev；分支不同会如实记录，不代表接口调用失败，也不能据此得出业务准确率。

如果密钥写在本机 `.env`，在 `npm run build` 后使用 Node 24 显式加载：

```bash
node --env-file=.env scripts/check-live.mjs --output reports/live-primitives-01.json
node --env-file=.env scripts/check-live.mjs --routes --output reports/live-routes-02.json
```

这些检查没有启动聊天主模型。要验证主模型能自行调用工具并完成原任务，请按[最小验收指南](docs/ACCEPTANCE.md)在独立练习目录中操作。

验证成功后，以相同环境重启 DSH。插件默认 `live`；没有 Key 时明确报错，不会悄悄切换为模拟结果。

## 4. 两个工具如何使用

### 通用判断 `jev_decide`

工具参数为 `state` 和 `questions`。完整可运行示例见 [examples/three-primitives.json](examples/three-primitives.json)。最小调用：

```json
{
  "state": {
    "task": "把会议纪要整理为行动清单",
    "notes": "小林周五前整理问卷结果。"
  },
  "questions": {
    "ready": {
      "type": "noul",
      "instructions": "state 中的材料是否足以完成 task 要求的整理？"
    }
  }
}
```

`type` 使用小写。`state`、`instructions` 支持文本、对象或数组；Choice 的 `criteria` 是选项描述映射，Score 是有序等级数组。问题 ID 只用于对应答案，判断条件必须写在 `instructions` 中。同一请求中的问题独立评估，不能引用另一题尚未产生的答案。

### 任务分流 `jev_route_task`

```json
{
  "task": "请修复仓库中日期解析函数对空字符串的处理，并补一个回归测试。",
  "context": "用户已指定当前仓库，可以先阅读文件定位函数。"
}
```

插件固定提出三道题：Choice 判断 `coding/research/writing/other`；Noul 判断核心目标是否需要澄清；Score 用三个等级估计复杂度。三个答案返回后，本地规则生成建议：

1. `needs_clarification.noul >= 0.8` → `clarify`。
2. 否则，Noul `> 0.2`、类别 confidence `< 0.8` 或类别为 `other` → `review`。
3. 其余 → `proceed`。Score 仅用于规划展示，不影响分支。

以上阈值是教学起点，没有经过业务数据校准。Choice 的最高选项概率与 confidence 不是同一个字段；Noul 不另造 confidence。`review` 意味着先读已有资料消除不确定，不要求每次都停下来询问用户。

模式提示还约定：用户澄清或读取材料产生新的关键事实后，只有新事实会影响判断才再分流一次；相同输入、普通进度与收尾总结不反复调用。该行为由主模型遵循提示词完成，核心会话样例已实测，范围与限制见真实联调记录。

成功结果顶层为 `status: "ok"`，建议位于 `recommendation.action`。失败为 `status: "error"`；分流工具同时返回 `action: "error"`，没有有效建议。通用客户端错误通过结构化值表达；DSH 自身的参数或权限错误则由其工具执行层报告。

## 5. 配置与边界

| 项目 | 默认值 / 行为 |
| --- | --- |
| `JEV_DECISION_MODE` | `live`；显式 `mock` 才使用人工夹具 |
| `TYPESAFE_DEFAULT_MODEL` | `jev-1.13.0`，记录请求模型与实际响应模型 |
| `TYPESAFE_API_KEY` | 仅从环境读取，不是模型可传的工具参数 |
| 端点 | 固定 `https://api.typesafe.ai/v1/systemone`，不跟随重定向 |
| 超时 | 默认 20 秒；可配置 100–120000 毫秒；遵循调用取消信号 |
| 自动重试 | 无，避免一次工具调用暗中重复请求 |
| 输入边界 | `state + questions` 默认 64 KiB，最多 16 题；JSON 最多 20 层 |
| 问题边界 | 本插件 Choice 2–32 选项；Score 2–10 等级；英文 ID 1–64 字符 |
| 响应边界 | 1 MiB；校验题号、类型、概率、Score 和用量 |

输入限制是本插件的实现边界，不等于 TypeSafe API 的全部限制。例如官方 Choice 支持更多选项。需要调整时，修改插件配置/验证器并补充相应测试。

高级配置可写在 `cordis.patch.yml` 中 `id: jev-decision` 的 `config`，字段包括 `mode`、`model`、`timeoutMs`、`maxInputBytes`、`confidenceThreshold`。**模式内有独立的工具实例**，需要在 `$DSH_HOME/.agent-presets/jev-decision/agent.cordis.yml` 对应行设置相同配置；环境变量适合统一设置所有实例的模式与模型。

插件只发送调用参数，不主动读取仓库、会话历史、文件或凭据。真实模式会把传入的 `state` 与 `questions` 发往 TypeSafe。它提供辅助判断；Jev 模式依靠提示词引导主模型调用工具，**不是强制执行的权限网关**。DSH 原有沙箱与审批继续负责其他操作，`proceed` 不授予额外权限。

## 6. 继续开发与验收

```bash
npm test                 # 离线测试：协议、异常、DSH 运行时、作用域和安装器
npm run demo             # 三条人工演示分支
npm run test:install     # 打包并用官方 CLI 在临时 home 安装；需要 pnpm 和依赖网络
```

- [实现设计](docs/ARCHITECTURE.md)：文件职责、请求链路与取舍。
- [交付与演示指南](docs/HANDOFF.md)：如何介绍项目、验收清单和后续工作。
- [最小验收指南](docs/ACCEPTANCE.md)：原任务范围、凭据配置、真实联调报告和聊天练习。
- [验证记录](docs/VALIDATION.md)：实际完成的检查与尚未验证的内容。
- [参考资料](docs/SOURCES.md)：官方协议、DSH 接口和版本说明。

移除时，先在 DSH 中切回其他模式并关闭相关会话，备份后移走本项目的 `jev-decision` 模式目录，再执行 `dsh plugin --profile <你的profile> remove dsh-jev-decision`。请勿删除整个 DSH home 或其他模式。
