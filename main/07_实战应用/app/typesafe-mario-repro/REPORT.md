# typesafe-mario 复现研究报告

> 本文件是完整研究报告（方法、数据、失败机制链、更正记录）。快速启动与项目概览见 [README.md](README.md)。

> **阅读范围：** 报告记录了多轮复现与后续扩展。上游源码仓库保持未修改，但本地运行器会 monkey-patch 解析器、策略或传输层；其中浏览器入口默认使用修正解析器、v2 harness 与 scripted pilot。请区分“上游源码”“本地复现扩展”和“真实 Jev 调用”：本文的 pilot 数据不构成 Jev 评测。

上游仓库：[`fhshaik/typesafe-mario`](https://github.com/fhshaik/typesafe-mario) @ `ca22449`（2026-09-15）
工作副本：`../typesafe-mario/`（原样克隆，未改动一行）

---

## 一句话结论

**在 NES 模拟器 + ROM 的本地环境上跑通了模拟器闭环**，策略判断由 scripted pilot 替代，未调用 Jev。在一条对照路径中观察到：
**`--display none`（headless）路径缺少跳跃按键的抬起沿，导致 Mario 撞上水管后卡住**
—— 基线卡在 x=594 不动 369 个决策，加上抬起沿后跑到 x=1124 并越过水管。

## 0. 关于 ROM 的更正（重要）

本报告早期版本称"本机没有 ROM"，据此实现了一个合成环境。**这个前提是错的。**

`gym-super-mario-bros` 9.1.0 —— 上游 `pyproject.toml` 声明的依赖 —— **把 ROM 打包在
已安装的 Python 包里**，`pip install -e ".[mario]"` 之后就已在本地：

```
.venv/lib/python3.13/site-packages/gym_super_mario_bros/_roms/super-mario-bros.nes   (40976 bytes)
```

我最初只在用户目录（`~/Downloads`、`~/Documents` 等）搜索 ROM，没有搜进虚拟环境，于是
基于错误前提继续推进。合成环境因此是对一个不存在的问题的解法；真实环境一直可用。

合成环境仍保留在仓库里，但**结论不再依赖它** —— 它的唯一价值是在受控条件下单独变化一个变量
（`ab_release_edge.py` 的 level 1），而真实 NES 模拟器环境证据（`ab_real_env.py`）才是决定性的。
真实环境下的复现见 §3.6，文件清单见 §8。

---

## 1. 上游在做什么

```
NES 模拟器 → 遥测/RAM 解析 → 结构化 JSON → Jev 选择动作 → 手柄输入
```

模型**看不到截图**。解析器把 RAM 与遥测压成一组按语义分组的事实：Mario 的位置/速度/离地状态、
跳跃轨迹、前方最多三个敌人的投影位置与接触时点、地形几何与观测可信度、实测推理延迟、
上一次控制的结果。Jev 在 7 个合法手柄宏（`noop` / `right` / `right_jump` / `right_run` /
`right_run_jump` / `jump` / `left`）中选一个，模拟器推进若干帧，循环往复。

每次请求同时问三个独立判断（`policy.py:56`）：

| 问题 | 原语 | 作用 |
|---|---|---|
| `next_action` | `Choice` | 选下一个手柄宏 |
| `jump_needed` | `Noul` | 此刻前跳是否有用 |
| `danger` | `Score` | 处境危险程度（供可视化） |

精确的时序算术留在代码里（如 `hazard.jump_must_start_this_decision` 由实测延迟、敌人运动、
动作节拍与跳跃腾空时间共同算出），Jev 只负责解释这些事实并做选择 —— 没有任何脚本化的兜底动作。

## 2. 复现方式：区分上游基线与本地扩展

| 输入 | 上游要求 | 本复现的处理 |
|---|---|---|
| ROM + 模拟器 | 合法获取的 SMB ROM + `nes-py` | **无需处理** —— ROM 随 `gym-super-mario-bros` 一起安装（见 §0），真实模拟器路径直接可用 |
| Jev API | `TYPESAFE_API_KEY` | 用本地替身回答以便离线复现；这只验证 mock 传输与策略管道，不验证 Jev 行为 |

**在 `repro_real_env.py` 指定路径中，除策略应答外使用上游闭环组件；浏览器入口另有本地扩展：**

- `run_episode` / `_run_realtime_dashboard` —— 上游运行器原封不动，包括线程化提交-回收、
  按键抬起沿处理、JSONL artifacts 写入；
- `TypeSafePolicy` —— 上游策略原封不动，构造真实的 `Choice`/`Noul`/`Score` 问题，
  调用真实的 `TypeSafeClient.system_one`，用真实 SDK 模型解码应答；
- `typesafe_sdk` —— 请求体是真实序列化产物，应答经真实 Pydantic wire 模型校验
  （`answers.next_action.choice/confidence/probabilities`、`noul`、`score`+`legend`）；
- `ACTION_TO_INDEX` —— 与真实 `gym_super_mario_bros.actions.SIMPLE_MOVEMENT` 逐项核对
  （索引 0–6 完全一致）。

浏览器入口 `viz_server.py` 还用 `CorrectedParser`、`MarioHarnessV2` 和 `AttemptMemory` 做本地实验扩展。因此它用于解释决策闭环及扩展实验，不是上游原版 dashboard 的等价运行，也不会访问真实 Jev。

**替身不是 Jev。** 本地 pilot 只读模型可见的状态 JSON，按固定规则作答，用来证明"管道通"，
不证明"Jev 会怎么打"。当前脚本显式替换了 transport；真实 Jev 运行请按上游 README 使用 CLI，不能只设置环境变量就把本地 mock 当成在线策略。

### 合成环境（受控实验用，结论不依赖它）

`--env synthetic` 走的是 `synthetic_nes.py`：一个与真环境同形状的无 ROM 世界。它存在的理由
不是"没有 ROM"，而是**能单独变化一个变量**（例如只改动作序列去隔离抬起沿的影响，见 §4.3）。
真实 NES 模拟器证据见 §3.6 与 §4.4。

三条规则被刻意做严，因为受控实验也必须在真实形状的输入上检验解析器：

1. **动作索引用真的** —— `step()` 索引真实的 `SIMPLE_MOVEMENT`。
2. **nametable 遵循 NES 寻址** —— 0x0500 处的瓦片缓冲是两个 16×13 nametable，
   关卡列号映射到页 `(level_x // 256) % 2`、页内位置 `(level_x % 256) // 16`，
   行距 16 字节；两页合起来覆盖关卡 512px 一段，相机过半后载入下一段。
3. **垂直坐标与解析器的支撑判定对齐** —— 解析器把 Mario 放在网格第 4 行，在其下两行内找实心瓦片，
   即地面瓦片行 `R` 支撑脚底位于行 `R` 的 Mario。这个常量写错会让每一帧都快照 `grounded=False`
   （开发过程中确实踩到过，见 §5）。

简化只在物理层，不在接口层：平坦瓦片世界、单一敌人（goomba）、无道具、无计分、恒定重力跳跃弧线。
上游决策循环观察不到这些 —— 它看到的每个数字都经由真实接口抵达。

## 3. 复现结果

### 3.1 仓库自带检查（真跑，无替换）

```
ruff format --check src tests   →  9 files already formatted
ruff check src tests            →  All checks passed!
python -m pytest -q             →  10 passed in 0.01s
```

环境：`uv venv --python 3.13`，`pip install -e ".[mario,dev]"`。
`nes-py 9.0.1` 在 Python 3.13 + arm64 macOS 上有现成 wheel，无需编译。

### 3.2 `state-demo`：喂给 Jev 的真实载荷（无 ROM、无 Key）

`.venv/bin/typesafe-mario state-demo` 直接打印模型输入，无需 API Key。载荷见
[`artifacts/sample_request.json`](artifacts/sample_request.json)（线上紧凑格式 4839 字节，
落盘的是缩进版所以文件更大）：

```
model: jev-latest
questions: next_action (choice, 7 criteria) / jump_needed (noul) / danger (score, 3 levels)
state: objective, level, player, trajectory, hazard, terrain, reaction_timing, recent_control, episode
```

`Choice` 的 instructions 分 8 组（`question`/`goal`/`timing`/`geometry`/`trajectory`/`stall`/
`enemy_timing`/`delay`），把"投影后距离而非当前距离""起跳窗口已过就现在跳"这类判断规则显式写进提示，
把算术留给代码。文本视图（`to_text()`）只用于调试与 UI，结构化对象才是规范形式。

### 3.3 dashboard 路径：通关（上游 README 推荐的运行方式）

```
episode outcome: STAGE CLEAR   decisions=50   last_logged_x=942   flag_x=960
latency_ms_median=125.6ms（模拟 120ms 往返）
模型侧观察到的反应延迟：last_inference_delay_frames=7
动作分布：right_run_jump ×38, right_run ×19
```

**决策数会浮动**（实测 50–57、`last_logged_x` 942–945）：dashboard 循环是线程化的实时循环，
"距离上次决策过了几帧"取决于推理实际耗时，所以每次运行的决策数不固定。这是真实行为，
不是不确定的测试 —— 与之相对，headless 路径按固定帧数批处理，完全确定。

截图：[`artifacts/dashboard/dashboard.png`](artifacts/dashboard/dashboard.png) —— 上游 `--screenshot`
的语义是"存第一帧有决策的画面"，所以画面停在 Decision 0001。面板上的 128ms 与模拟的 120ms 吻合，
概率条/危险分值/状态区全部正常渲染。

**通关判定说明**：每条 JSONL 记录存的是该批动作**执行之前**的状态，所以通关只体现在最后一条的
`terminated=true` 上，日志里最后可见的 x 永远差一截（942→960 这 18px 落在最后一批里）。
这是读取 artifacts 时的一个陷阱 —— 单看 `episode.stage_clear` 会把通关误读成"没通关"或"不明原因结束"。
[`verify_outcome.py`](verify_outcome.py) 用独立重放消除这个歧义。

### 3.4 headless 路径：同样的世界、同样的策略，坠坑

```
--display none:  heuristic → death @ x=285
                 typesafe  → death @ x=285（决策 13 的动作批内死亡）
```

`verify_outcome.py` 重放该日志，逐条位置与合成世界完全吻合（日志是忠实轨迹），确认死因是坠入
第一个坑（列 16–17，x=256–288）。

两个策略**都**死在同一个位置，且死亡位置恰好是坑 —— 这不是策略能力问题，是路径问题。§4 给出证明。

### 3.5 瓦片寻址校验：跨 nametable 页翻转全对

上游自带测试只在 `x_pos≈100`（相机停在 0）时解析过，第一屏之后从没测过。
[`verify_parser.py`](verify_parser.py) 让 Mario 走过多个 256px 块，把解析器的 `local_grid`
与从合成世界直接算出的真值逐格比对：

```
PASS: every resident grid cell matched ground truth at all camera offsets,
      including across two nametable page flips (page 0 -> 1 -> 0).
```

7 个采样点覆盖 `相机未启动 → 刚启动 → 页 0→1 边界 → 页 1 → 第二窗口 → 页 1→0 → 页 1`，
地形派生量（`gap_distance_tiles` / `obstacle_distance_tiles` / `obstacle_height_tiles` /
`clear_forward_tiles`）同步一致，敌人相对位置与格标记也正确。

### 3.6 真实环境（作者的原始模拟器 + 真实 ROM）

```bash
$PY repro_real_env.py --decisions 300
```

这条路径使用模拟器、ROM 和上游闭环组件；模型 HTTP 一跳由 scripted pilot 代答。因此结果反映本地策略与执行链，不反映 Jev 的决策质量。

真解析器读取真 NES 内存在 1-1 开局的表现（`grounded=True`、9 行网格正确、
地形摘要正常）确认了接口对齐：

```
REAL ENV through the REAL PARSER
grounded: True | jump_phase: grounded
local_grid:
    ...........
    ...........
    ...........
    ...........
    ..M........
    ...........
    ###########
    ###########
    ...........
terrain: {geometry_available: True, obstacle_ahead: False, clear_forward_tiles: 8, ...}
```

跑 300 个决策的结果：

| 策略 | 决策数 | 最远 x | 结局 |
|---|---:|---:|---|
| heuristic | 14 | 309 | 撞上第一只板栗仔死亡 |
| scripted pilot（历史日志名 typesafe） | 300 | 594 | **卡在水管前**（369 个决策原地不动） |

`heuristic` 撞板栗仔属预期行为（它就是"一直往前跑"，上游 README 也明说它不是基准）。
`typesafe` 的卡死则是缺陷，见 §4.5。

## 4. 发现：headless 路径缺少按键抬起沿

### 4.1 缺陷本身

SMB 在 A 键的**按下沿**起跳，按住不放只跳一次。上游两条显示路径在这一点上不一致。

`runner.py:162` 的 dashboard 循环处理了这件事：

```python
if decision_updated and action in JUMP_ACTIONS and snapshot.grounded:
    # A new jump macro needs a button-up edge before A is pressed again.
    action = JUMP_RELEASE_ACTION[action]
```

`run_episode` 的 headless 分支（`--display none`，上游 README 称为 headless benchmark）没有任何等价处理，
它把同一个 `action_index` 连续喂 `frames_per_decision` 帧。

后果：当策略在连续两个"已落地"的决策上选择跳跃宏 —— 也就是"落地没跳够、想再跳一次"这个再自然不过的情形 ——
headless 下 A 一直是按住的，第二次起跳不会发生，Mario 贴着地面撞进下一个障碍。

### 4.2 触发条件（精确刻画）

固定 8 帧/决策、同一种子、同一世界，只变动作序列：

| 动作序列 | 结局 |
|---|---|
| 一直 `right_run_jump` | x=285 坠坑 |
| `right_run` / `right_run_jump` 交替 | x=554 坠坑（更远，但仍死） |
| `right_run` / `right_run_jump` ×2 交替 | x=287 坠坑 |
| 一直 `right_run` | x=285 坠坑 |

**只要连续两次决策都落在跳跃宏上，headless 就失效**；中间夹一次非跳跃宏就能缓解。
dashboard 路径因为插了释放帧，没有这个问题。

### 4.3 A/B 对照（决定性）

[`ab_release_edge.py`](ab_release_edge.py) 两级实验。Level 1 完全脚本化、不涉及任何策略，
唯一变量就是抬起沿：

```
=== level 1: 一份固定动作序列，无策略介入（决定性）===
variant                  jumps_started release_frames  final_x       outcome
A held (as shipped)                  2              0      285         death
release edge added                  10              9      960   stage_clear

=== level 2: 同一序列经由真实 headless run_episode ===
variant                  decisions  injected       outcome  final_x
A held (as shipped)              14         0 budget_exhausted      285
release edge added               49         9   stage_clear      960
```

同一序列、同一世界、同一种子：**起跳 1 次 vs 10 次，x=285 坠坑 vs x=960 通关**。
Level 2 确认这个效应能穿过真实运行器的批处理与日志，不只是手写循环里的产物。

### 4.4 真实 NES 模拟器上的决定性证据

合成环境的对照见 §4.3；下面是在**真实模拟器 + 真实 ROM**上重做的同一个实验
（`ab_real_env.py`），这才是这个发现的分量所在。

World 1-1 的第一座高水管在 x≈608，`x=594` 正是被它挡住的位置：

```
real emulator, real ROM, real TypeSafePolicy, real run_episode
variant                   max_x  decisions_at_max_x  release_frames
baseline (as shipped)       594                 369               0
with release edge          1124                   1               5
```

| 指标 | 基线（原样） | 加上抬起沿 |
|---|---:|---:|
| 最远到达 | x=594（水管前） | **x=1124** |
| 卡在该位置不再前进的决策数 | 369 / 400 | 1 / 400 |
| 空中决策数 | 15 | 48 |
| 越过水管（x>608）的决策数 | **0** | 34 |
| 实际起跳次数（grounded→rising） | 2 | 7 |

基线那段日志把失败机制写得非常清楚：策略连续 269 次选择 `right_run_jump`，
而 `jump_phase` **269 次全部是 `grounded`** —— 模型正确识别出"前方 1 格处有 3 格高的障碍、
需要起跳"，反复下令起跳，而输入层每次都没能真正起跳，Mario 就一直顶着水管走。

这是这个缺陷最严重的一面：**它不是"跳得不好"，而是"指令根本没被执行"**，
而模型对此完全无从知晓 —— 状态里没有"你的起跳请求被忽略了"这个事实。

### 4.5 结论的边界

- NES 模拟器证据已经确凿：同一环境、同一策略、同一 ROM、同一种子，唯一变量是抬起沿。
- 触发取决于策略输出的动作序列：只要连续两次决策落在跳跃宏上就会踩到。一个总在跳跃间
  插入 `right_run` 的策略不会触发它 —— 这是**路径间不一致**，不是"跑不起来"。
- `--display none` 的定位是 headless benchmark，可能被视为"简化路径"；但从"同一策略在两条
  路径下应得到同样结果"看，这是一个应当修复的差异。
- 未验证的是真实 Jev 的决策质量 —— 需要 API Key（见 §7）。

## 5. 复现过程中修正的自身错误（供后来者避坑）

这些不是上游问题，是我在建模时踩的坑，列出来因为它们都可能被误当成上游缺陷：

1. **地面行常量错位** —— 最初把地面放在第 10 行，而解析器的支撑判定要求地面落在脚下两行内，
   结果每一帧 `grounded=False`、`jump_phase=airborne`。改到第 8 行后语义立刻正常。
   解析器没有错，是我的世界坐标与它的约定不一致。
2. **相机与 nametable 不同步** —— 最初在更新相机**之后**写 RAM，导致瓦片缓冲描述的窗口与相机不符。
   真实硬件的 nametable 不可能与相机矛盾（游戏每帧一起更新），所以这是建模顺序错误而非解析器缺陷。
   修掉后跨页翻转全部通过。
3. **走离平台不转为空中** —— `_resolve_vertical` 只在非着地时调用，导致 Mario 从坑上"走"过去。
   补上每帧支撑判定后，走离边缘 → 转空中 → 坠落死亡，语义正确。
4. **通关被误读** —— 见 §3.3，最后一条日志的 `terminated=true` + `stage_clear=false`
   既可能是通关也可能是坠坑；`verify_outcome.py` 用重放判定，别靠读日志猜。

## 6. 未验证部分（及如何补齐）

| 项 | 状态 | 补齐方式 |
|---|---|---|
| 真实 ROM 上的行为 | **已验证** | `gym-super-mario-bros` 自带 ROM，见 §3.6 与 §4.4 |
| Jev 的真实决策质量 | **未验证** | 按上游 README 配置真实 API 并运行上游 CLI；当前浏览器 mock / v2 harness 不支持把环境变量当作一键切换 |
| 真实 API 延迟与 8 帧节拍是否匹配 | **未验证** | 需真实 Key 测量；本复现只能模拟（60ms → 约 5 帧，120ms → 7 帧） |
| `--display game` 路径 | 未测 | 需真实渲染窗口（`--display dashboard` 与 `none` 都已跑过） |
| 上游其余文件（`cli.py` / `dashboard.py` / `tests/`） | 未逐行审计 | 本次只读了决策闭环相关路径 |

浏览器 mock 路径没有经过真实 Jev 验证，不应通过随手设置环境变量就宣称切换成功。真实模型试用请直接按上游 README 使用 `typesafe-mario play`；若要在线评测本地扩展，应另行实现、记录并验证 API transport。

## 7. 本地可视化服务

```bash
../typesafe-mario/.venv/bin/python viz_server.py --port 8770            # 真实模拟器 + 内置 ROM
../typesafe-mario/.venv/bin/python viz_server.py --env synthetic        # 合成对照环境
```

浏览器打开 <http://127.0.0.1:8770/>，即可观看决策循环。默认使用 NES 模拟器和 RAM；服务复用上游 runner / dashboard protocol，同时以本地 `WebDashboard` 发布遥测，并 monkey-patch `CorrectedParser` 与 `MarioHarnessV2`。HTTP hop 由 scripted pilot 替代，因此这一页是本地扩展示范，不是未经修改的上游 baseline，也不是真实 Jev 调用。

页面上能看到：

- **游戏画面**：256×240 实时帧，以原始 RGBA 直传（不编码，浏览器端解码）；
- **本地 pilot 示意输出**：选中的动作、候选分布、mock 置信度、模拟延迟、累计回报；
- **七个手柄宏的示意分布**：由规则 pilot 生成，不是 Jev 概率；
- **处境判断示意**：mock 的 `Noul` / `Score` 数值，
  反应地平线帧数、`jump_must_start_this_decision` 是否为真；
- **原始调试网格** `local_grid` 与地形摘要；原始网格不会发送给 Jev，结构化 `terrain` / `hazard` 特征才会进入 state；
- **进度曲线**：每次决策一个点，落地决策为蓝色、空中为橙色，旗杆 960 画成红线；
- **发给本地 pilot 的结构化 JSON state**（可展开）；

控件：重新开始 / 暂停 / 自动重开开关 / 画面速率（12–240 帧每秒）/ 保存截图。

服务接口（也可单独取用）：

| 端点 | 用途 |
|---|---|
| `GET /frame.rgba` | 当前帧原始 RGBA 字节（256×240×4） |
| `GET /snapshot.png` | 当前帧 PNG |
| `GET /state.json` | 当前决策的全部遥测 |
| `GET /model_input.json` | 发给本地 pilot 的结构化 state 对象 |
| `GET /history.json` | 每个决策一条的进度序列 |
| `POST /control` | `{"command": "restart"｜"pause"｜"resume"｜"speed"｜"auto_restart", ...}` |

**自动重开**：上游 dashboard 在本局结束后会保持打开、等人按 R；服务化观看需要连续对战，
所以默认在本局结束 2 秒后自动重开（留出看到结局的时间），页面上可关闭。战绩统计（总局数、
通关次数）实时显示。

> 注意：本地 pilot 替身是个**固定规则的简单策略**（"该跳就跳、否则向前跑"），不是 Jev。
> 它经常过早起跳而撞上敌人 —— 上表里的通关数只描述该规则策略。页面可以暴露失败状态，
> 但不能据此评价 Jev，也不能证明 harness 会提升模型表现。

## 8. 文件清单与运行方式

```
typesafe-mario-repro/
├── repro_real_env.py       真实模拟器 + 真实 ROM 上的完整闭环（主要复现）
├── ab_real_env.py          NES 模拟器上的抬起沿 A/B（决定性证据）
├── synthetic_nes.py        无 ROM 的同形状 NES 环境（受控实验用，非必需）
├── repro_run.py            决策闭环 + headless 路径对照（合成环境）
├── repro_dashboard.py      上游 README 推荐的 dashboard 路径，跑到通关 + 截图
├── viz_server.py           浏览器实时可视化服务（本地上看它玩）
├── verify_parser.py        瓦片寻址跨相机位置的逐格真值校验
├── verify_outcome.py       重放日志判定真实终局（消除 artifacts 的歧义）
├── ab_release_edge.py      抬起沿缺陷的两级 A/B 对照（决定性证据）
└── artifacts/              全部产物：sample_request/response、各路径 JSONL、报告、截图
```

```bash
cd typesafe-mario-repro
PY=../typesafe-mario/.venv/bin/python

$PY viz_server.py --port 8770                          # 实时可视化，真实模拟器（浏览器打开）
$PY repro_real_env.py --decisions 300                   # 真实 ROM 上的完整闭环
$PY ab_real_env.py --decisions 400                      # NES 模拟器 A/B：抬起沿（决定性）
$PY verify_parser.py                                   # 瓦片寻址校验（合成环境）
$PY repro_run.py --episodes 1                          # headless 闭环（对照）
$PY repro_dashboard.py --screenshot --delay-ms 120      # dashboard 路径，跑到通关
$PY ab_release_edge.py                                  # 抬起沿 A/B
$PY verify_outcome.py <run.jsonl> [--mode dashboard]    # 判定某次 run 的真实终局
```

环境依赖已装在 `../typesafe-mario/.venv`（Python 3.13.14 / typesafe-sdk 0.7.0 /
gym-super-mario-bros 9.1.0 / nes-py 9.0.1 / pygame 2.6.1 / numpy 2.5.3）。

## 9. 附：值得记下的上游设计

- **状态不带截图**：把 RAM 压成"按含义分组的事实"，而不是像素或散文。这是让 `Choice`
  在 7 个宏上做概率判断、且判断可解释的前提。
- **算术与判断分离**：`jump_must_start_this_decision`、`takeoff_deadline_frames`、
  `will_land_before_contact` 这类量都由代码算准，模型只解释。提示里明确写"用投影后距离，不要只看当前距离"。
- **实测延迟进入状态**：`reaction_timing.last_inference_delay_frames` 把上一次推理的真实延迟回灌进状态，
  敌人威胁用"反应地平线"（`decision_horizon_frames + last_response_delay_frames`）计算。
  这是把推理延迟当物理量对待，而不是假装它不存在。
- **不做动作覆盖**：上游 README 明确"没有任何脚本化的兜底动作"，即便代码已经算出"必须现在起跳"，
  最终仍由 Jev 决定。代价是可能错过窗口，收益是决策权完整保留在模型侧 —— 这正是本项目要演示的命题。

## 10. JevHarness 式 harness v2：一次反思驱动的尝试（负结果 + 一条实质发现）

参考 [`TianyuCodings/JevHarness`](https://github.com/TianyuCodings/JevHarness)（"Reason deeply
during development. Freeze the strategy. Let Jev make fast, fuzzy decisions."），以它的三个模式
重写了马里奥 harness（`mario_harness_v2.py`，上游零改动）：

| JevHarness 模式（宝可梦样例） | 马里奥 v2 的对应实现 |
|---|---|
| 状态带**预计算衍生事实**（伤害竞争：几回合 KO） | `takeoff_window`：从实测跳跃弧（峰值 68px/47 帧/跨度 82px）推出起跳窗口，对每个障碍/坑给出 `jump_now / wait / too_late / regain_speed` 判定 |
| **每个动作的 criterion 带本局量化后果**（"68% HP、2 回合 KO"） | 每个手柄宏的 criterion 按当前判定动态重写（"4 格障碍 64px 外，窗口 55–83px：现在起跳"） |
| instructions 是**策略陈述**（"有 KO 就拿"） | "verdict 说 jump_now 才跳；说 wait 就继续跑——早跳和晚跳一样必死" |
| memory 经反思更新 | 原始死亡记录蒸馏为 per-hazard 教训（"此处起跳过早，靠近窗口边缘再跳"） |

`harness_ab.py` 在 NES 模拟器中（同 ROM、同种子、双臂都带抬起沿 wrap）跑了 A/B，随后按数据做了
3 轮反思修复（速度单位错 8 倍、空中松键、贴墙死锁）——完整复刻了 JevHarness 的
reflection→propose→evaluate 循环。

### 结果

| 配置 | v1（上游原装） | v2（JevHarness 式） |
|---|---:|---:|
| 8 帧/决策（上游默认） | best_x=1124 ×6 局 | best_x=900 ×6 局 |
| **4 帧/决策** | **best_x=3156 ×6 局** | best_x=1517 ×6 局 |

### 结论

1. **决策粒度是第一约束，比任何提示词工程都值钱**：`--frames-per-decision` 从 8 降到 4，
   同一策略 best_x 提升 2.8 倍（1124→3156）。机制：4 格水管的起跳窗口实测仅 28.6px 宽，
   而 8 帧粒度一拍就跨 21px——判定经常整拍错过窗口。**这是对上游 harness 的实质优化建议。**
2. **v2 输给 v1（负结果，诚实记录）**：规则替身下，v1"3 格内就跳"的粗糙启发式在细粒度下
   近似"高频连跳"，对连续水管段意外地强；v2 的精确窗口判定每次落地后需重新加速，窗口边缘
   的时机赌注仍然会错拍。
3. **为什么这不否定 JevHarness**：JevHarness 的收益前提是判断者（Jev）会*读*事实与教训文本。
   规则替身不读文本——记忆注入后 6 局行为逐字节相同，正是因为替身只响应 verdict 数值。
   所以本 A/B 验证的是**harness 管道**（payload 组装、记忆注入、真实性校验）而非模型收益；
   替身里的 v2 劣势说明的是"这套窗口规则写得不如连跳启发式"，不是"结构化事实没用"。
   要测真实收益，需要为本地扩展单独接入并验证真实 API transport；`harness_ab.py` 当前固定使用规则替身，设置 `TYPESAFE_API_KEY` 不会自动把它变成 Jev 评测。

文件：`mario_harness_v2.py`（v2 harness + 判定逻辑 + 教训蒸馏）、`harness_ab.py`（A/B 驱动），
产物在 `artifacts/harness_ab/`。这些对照在 NES 模拟器 + ROM 上运行，由本地策略替身作答；上游仓库源码未改动，但 harness 行为有本地扩展。

## 11. 发现：上游地形网格的相机页错位会污染派生事实（用户观察触发）

分享展示时用户发现：「调试网格看不到坑，Mario 却总在附近失败」。追查发现，上游 parser 的原始网格可能与滚动相机错位。注意：`local_grid` 只用于调试，不直接发送给 Jev；由网格派生的 `terrain` / `hazard` 特征会进入结构化 state，因此解析错误仍可能影响后续判断。

**机制**：`MarioStateParser._extract_local_grid` 用**关卡绝对坐标**对 0x0500 的双页
nametable 采样（`page = (x // 256) % 2`）。但游戏模拟器中这对页面跟随相机滚动，缓冲覆盖的
关卡窗口是 `[256×⌊camera/256⌋, +512)`。相机落在**奇数** 256px 页时，上游的页选择恰好
错开一页（错位 256px）——大约一半的游玩位置。

**实测**（`grid_evidence` 取证，Mario 在 x=1094、相机 971、⌊971/256⌋=3 为奇数）：

```
上游 parser 的调试网格：     修正后的调试网格：
  ..M........                ..M........
  ..M........                #.M........
  ..M........                ..M........
  ..M........                ..M........
  ..M........                ..M........
  ..M........                ..M....##..
  ..M........                ..M....##..
  ..M........                ..M....##..
  ..M........                ..M....##..
```

调试网格里 Mario 看似悬浮在**一片虚空**里——没有坑、没有地面、没有管道。地形事实
（`obstacle_ahead`、`gap_distance_tiles`）由网格推导，因此结构化 state 也可能携带错误的
地形信息。mock pilot 的失败位置与修正后的网格变化能帮助定位 parser 问题，但不能断言
真实 Jev 当时“看见了什么”或证明所有重复死亡均由这一问题造成。

**修复**（`parser_fix.py`，复现层，上游零改动）：`CorrectedParser` 子类化上游解析器，
parse 后用相机推导基址（`camera = x - ((ram[0x86]-ram[0x071C]) % 256)`，
`base = 256×⌊camera/256⌋`）重建 11×9 网格并替换进冻结快照。所有下游派生事实
（terrain、起跳窗口判定）自动修正，因为它们从 `local_grid` 惰性推导。
`viz_server` 与 `harness_ab` 均已接入。浏览器页把原始网格标为调试视图，并明确说明它不发送给模型。

**修复后效果**（28 局实时观察）：死亡从「全部堆在同一坑位」打散为
`[843, 843, 843, 843, 1149, 1416]`——一局越过了此前从未通过的 1104 坑并推进到 1416。
当前替身仍卡在 x=722/843 的 4 格高双管段：这说明当前规则策略仍受连续起跳时机限制；本结果仅是本地 mock 策略行为。修复后网格对齐改善，可作为 parser 证据，但不构成 Jev 策略验证。

## 许可与合规

上游仓库未附 LICENSE，且声明不含任何 Nintendo ROM 或游戏数据。
本复现不含 ROM、不含游戏数据，模拟器环境完全由代码合成；使用的 ROM 需自行合法获取。
本目录代码为复现目的编写，与上游作者无关。
