<p align="center">
  <img src="media/header.svg" alt="pg-jev — ask your Postgres tables questions in plain language" width="100%">
</p>

# jev — 用自然语言向你的 Postgres 表提问

[![CI](https://github.com/realZachi/pg-jev/actions/workflows/ci.yml/badge.svg)](https://github.com/realZachi/pg-jev/actions/workflows/ci.yml)
[![PGXN](https://badge.fury.io/pg/jev.svg)](https://pgxn.org/dist/jev/)
[![License](https://img.shields.io/badge/license-PostgreSQL-blue.svg)](LICENSE)
[![Website](https://img.shields.io/badge/website-pgjev.com-0a56cf.svg)](https://pgjev.com)

按你平常说话的方式写出条件，剩下的交给 Postgres。

`jev` 让你用自然语言条件对行进行过滤、排序和分类。每一行都由
[TypeSafe 的 Jev](https://docs.typesafe.ai) 来评判——这是一个返回校准概率而非生成文本的 System One
模型。无需索引、无需嵌入、无需向量列。

网站：[pgjev.com](https://pgjev.com)

```sql
CREATE EXTENSION jev CASCADE;

SELECT * FROM people WHERE jev(people, 'the name is European');

SELECT subject, jev_prob(tickets, 'the customer is angry') AS p
FROM tickets ORDER BY p DESC LIMIT 20;

SELECT jev_choice(tickets, 'which team should handle this?',
                  ARRAY['billing', 'technical', 'security', 'sales']) AS team, count(*)
FROM tickets GROUP BY 1;

SELECT name, jev_score(products, 'how luxurious is this product?',
                       ARRAY['budget', 'mid-range', 'premium', 'luxury']) AS luxury
FROM products ORDER BY luxury DESC;
```

`jev()` 是一个普通的布尔函数，因此可以与 SQL 中的其他一切组合使用：`AND age > 40`、
连接、`GROUP BY`、`LIMIT`、`ORDER BY jev_prob(...)`。

## 工作原理

1. `jev(table, 'condition')` 以复合值的形式接收行。对某张表 + 某个条件的首次调用会启动一次预读，
   按物理顺序流式读取该表（TID 范围扫描；视图则按 `OFFSET` 翻页）。
   `jev.max_prefetch_rows` 限制其为找到被请求的行而搜索的距离，以及保留的跳过行数；
   它不限制答案缓存或会话总内存。
2. 行按每个请求 `jev.batch_size`（20）行打包进一个共享*状态*
   （`{"condition": ..., "rows": [...]}`），每行对应一个是/否
   [Noul](https://docs.typesafe.ai/primitives/noul) 问题。Jev 在一个状态上并行评估所有问题，
   从而摊薄约 270 token 的请求开销（单独一行约 435 token，而按 20 行一批时每行约 175 token）。
3. 最多有 2 × `jev.concurrency` 个请求通过持久 HTTPS 连接在途，每一行在其批次返回后即得到答案，
   因此 `LIMIT` 会在在途窗口之后停止预读；而在 `jev()` 运行之前就被成本更低的谓词过滤掉的行
   （`WHERE age > 60 AND jev(...)`）会被直接跳过，而不是送去评判。
4. 答案按行内容与问题为后端会话缓存，因此只要这些答案仍在缓存中，重新运行、更改阈值或按概率排序
   都是零成本的。缓存会随唯一的行/问题对不断增长，直到 `jev_cache_clear()` 清除它或后端会话结束。
   来自子查询或 CTE 的行（匿名 `record` 类型）无法预读，只能一次一个请求地评判；尽量把 `jev()`
   放在基表或视图上。

在一张 2,000 行的欧洲数据表上实测（到 API 约 190 ms）：首次运行约 3.5 s、共 100 个请求、约 296k
输入 token、约 $0.012；第二次运行约 50 ms；对新条件执行 `LIMIT 3` 约 0.6 s。在一个仍保有连接池中
连接的会话（空闲时间小于 `jev.keepalive`）里执行新条件约需 2.3 s：每条新连接上的第一个请求是最慢的。
版本 0.1.0 完整查询需要 8.5 s（338k token），`LIMIT` 需要 8.4 s。

### 为什么每个请求 20 行

Jev 需要按位置在数组中找到 `rows[i]`，而数组一长这就变得不可靠。以结构化列（职位、是否欧盟成员、
自由文本字段中的某个短语；各 400 行）的真值为对照，1–20 行的批次 100% 正确，40 行的批次为
92–98%，80 行的批次为 77–94%。更宽的行（1,000 字符）在 20 行批次下没有影响。给行命名而非按索引
引用也没有帮助。20 行批次比 40 行批次多花 4% 的 token，但速度一样快，因为请求的延迟几乎不取决于其
大小。

## 安装

环境要求：PostgreSQL 14–17 并带 `plpython3u`（Debian/Ubuntu 上的软件包为
`postgresql-plpython3-NN`，EDB 与 Postgres.app 构建已内置）、超级用户权限，以及来自
https://console.typesafe.ai 的 TypeSafe API 密钥。不开放超级用户或 `plpython3u` 的托管主机
（Supabase、Neon、RDS……）无法运行本扩展；参见[可用环境](https://pgjev.com/docs/getting-started/where-it-runs)。

### 借助 AI 智能体（最简单）

本仓库附带一个 [agent skill](.agents/skills/pgjev/SKILL.md)，发布在 [skills.sh](https://skills.sh)
上。把它安装到你的项目中，然后让 Claude Code、Codex、Cursor 或任何其他支持 skill 的智能体完成
剩下的工作：

```bash
npx skills add realZachi/pg-jev
```

> 在这台服务器上安装 pgjev 并完成设置。

智能体会执行预检（PostgreSQL 版本、`plpython3u`、超级用户），针对正确的 `pg_config` 运行
`pgxn install jev` 或 `make install`，执行 `CREATE EXTENSION jev CASCADE`，配置 API 密钥并运行
冒烟测试。之后它还知道如何编写注重成本的 `jev()` 查询（“找出客户威胁要取消的工单”），以及解释
pgjev 能做什么。这些文档也以 Markdown 形式供智能体阅读：在 https://pgjev.com/docs 下任意页面
的 URL 后追加 `.md` 即可（参见[面向智能体](https://pgjev.com/docs/for-agents)）。

### 通过 PGXN 安装

```bash
pip install pgxnclient       # once; also available as `pgxn-client` in Debian/Ubuntu and Homebrew
pgxn install jev             # downloads the release from pgxn.org and runs `make install` against pg_config on PATH
psql -c "CREATE EXTENSION jev CASCADE"
```

当服务器的 `pg_config` 不在 PATH 上，或扩展目录不可写时，使用
`pgxn install jev --pg_config=/path/to/pg_config`（或 `sudo pgxn install jev`）。

### 从源码安装（PGXS）

```bash
git clone https://github.com/realZachi/pg-jev.git && cd pg-jev
make install            # uses pg_config on PATH; or: make install PG_CONFIG=/path/to/pg_config
psql -c "CREATE EXTENSION jev CASCADE"   # superuser required (plpython3u is untrusted); CASCADE creates plpython3u
```

### Docker

```bash
docker build -t pg-jev .                       # add --build-arg PG_MAJOR=17 for another major
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=pw -e TYPESAFE_API_KEY=your-key pg-jev
psql postgres://postgres:pw@localhost/postgres -c "CREATE EXTENSION jev CASCADE"
```

### API 密钥

既可以在 PostgreSQL 服务器进程的环境中导出 `TYPESAFE_API_KEY`，也可以按会话或按角色设置：

```sql
SET jev.api_key = 'your-key';
ALTER ROLE analyst SET jev.api_key = 'your-key';   -- persistent, per role
```

### 本地 Jev 兼容服务器

`jev.api_url` 可以指向任何使用同一 `POST /v1/systemone` 契约的服务器，这样行数据永远不会离开
你的网络，也没有按行计费。这类服务器有两个：[stuntd](https://github.com/bladedevoff/stuntd)
（把 Laya 放在 Jev API 之后；它还会记录答案并为每个问题训练一个 head，因此一张表的决策可以随时间
逐步迁移到本地）以及 laya-server：

```sql
SET jev.api_url = 'http://127.0.0.1:8787/v1/systemone';   -- stuntd's default address
```

只有 `*.typesafe.ai` 主机才需要 API 密钥。对于其他任何主机，未设置密钥时请求不带 `Authorization`
头发送，设置了密钥则带 `Bearer <key>`。无论后端是哪台服务器，`jev_stats()` 和提示信息中的
token 计数与成本估算都按 TypeSafe 的标价计算。

## 函数

| 函数 | 返回值 | 用途 |
| --- | --- | --- |
| `jev(row, condition [, threshold])` | boolean | `WHERE` 谓词。阈值优先级：参数 → `jev.threshold` → 0.5 |
| `jev_prob(row, condition)` | float8 | 该行满足条件的概率，取值 0..1 |
| `jev_score(row, question, levels text[])` | float8 | 在有序档位上的概率加权位置（0 .. n-1） |
| `jev_score_norm(row, question, levels)` | float8 | 同上，归一化到 0..1 |
| `jev_choice(row, question, options text[])` | text | 该行最可能的选项 |
| `jev_confidence(row, question, kind, options)` | float8 | `score`/`choice` 答案的置信度 |
| `jev_eval(row, question, kind, options)` | jsonb | 完整原始答案（概率、图例、置信度） |
| `jev_stats()` | jsonb | 本会话的请求数、token 数、估算成本、缓存命中数、在途请求数与连接池连接数 |
| `jev_cache_clear()` | void | 清除已缓存的评判结果 |
| `jev_version()` | text | 扩展版本 |

`row` 就是表别名本身（`jev(people, ...)`），或者子查询的别名。

## 设置

所有设置都是普通的 GUC：`SET jev.<name> = ...`、`ALTER ROLE ... SET`、`ALTER DATABASE ... SET`
或 `postgresql.conf`。

| 设置 | 默认值 | 含义 |
| --- | --- | --- |
| `jev.api_key` | 环境变量 `TYPESAFE_API_KEY` | TypeSafe API 密钥。当 `jev.api_url` 不是 `*.typesafe.ai` 主机时可不设置 |
| `jev.model` | `jev-latest` | 模型名称或固定版本，如 `jev-1.13.0` |
| `jev.threshold` | `0.5` | `jev()` 返回 true 的概率阈值 |
| `jev.batch_size` | `20` | 每个 API 请求的行数。超过约 20–25 行后准确率会明显下降（见上文） |
| `jev.concurrency` | `16` | 并行 API 请求数；在执行器之前排队的请求数最多可达其两倍 |
| `jev.max_prefetch_rows` | `5000` | 预读搜索的距离以及保留的跳过行数；不是对答案缓存或会话总内存的上限 |
| `jev.notices` | `on` | 每完成一个请求发一条进度 `NOTICE`，每张表发一条汇总（请求数、token、估算成本与耗时） |
| `jev.api_url` | `https://api.typesafe.ai/v1/systemone` | 端点（代理、mock、本地 Jev 兼容服务器，如 stuntd 的 `http://127.0.0.1:8787/v1/systemone`；见上文） |
| `jev.timeout` | `30` | 每个 API 请求的秒数。等待可被中断：`statement_timeout` 和取消请求会在 250 ms 内生效 |
| `jev.keepalive` | `600` | 连接池中的 API 连接可空闲的秒数，超过后重连。新连接上的第一个请求需付出一次 TLS 握手，加上实测高达 1.5 s 的服务端初始化开销，因此应让连接跨查询保持存活；TCP keepalive 探测可捕获被静默断开的连接 |
| `jev.max_rows_per_statement` | `0`（关闭） | 中止会向 API 发送超过此数量行数的语句。面向共享部署的花费护栏 |
| `jev.max_chars_per_statement` | `0`（关闭） | 同上，按行数据的字符数计 |

## 如何写好条件

Jev 会按字面回答你写下的问题。以下几点会有帮助（更多信息见
[TypeSafe 文档](https://docs.typesafe.ai/model-jaggedness/jev-1.13)）：

- 写明确切的条件：`'the customer threatens to leave, dispute a charge, or take legal action'`
  优于 `'churn risk'`。
- 算术、日期和精确匹配留在 SQL 里；让模型判断语义。
- 在选定阈值之前先用 `jev_prob()` 查看分布。模棱两可的行确实会落在 0.5 附近。
- 只发送评判所需的列：创建一个包含相关列（以及任何预过滤）的视图，然后对视图调用
  `jev(view_alias, ...)`。视图会像表一样被预读和分批。

## 注意事项

- 这在设计上就是全表扫描：执行器询问到的每一行都会发往 API。同一个 `WHERE` 中成本更低的谓词会
  先运行，其淘汰的行会被跳过；`LIMIT` 会提前停止；`jev.max_rows_per_statement` 限制花费。
- 行内容会被发送到第三方 API。不要在不可共享的数据上使用。
- 答案缓存位于后端会话中（PL/Python `GD`），会随唯一的行/问题对增长；
  `jev.max_prefetch_rows` 不对它设限。`jev_cache_clear()` 清除当前会话的已缓存答案和预读状态，
  结束后端会话即释放缓存。拥有大量会话的连接池中，每个会话各自预热自己的缓存。
- `plpython3u` 是非受信语言：只有超级用户能创建该扩展，且函数以服务器的操作系统权限运行。

## 开发

```bash
make docker-test                 # builds test/Dockerfile and runs the regression suite (PG_MAJOR=16 by default)
make docker-test PG_MAJOR=17
```

在本地有正在运行的服务器且 `pg_config` 位于 `PATH` 时：

```bash
make install
python3 test/mock_api.py &       # deterministic stand-in for the TypeSafe API
make installcheck                # pg_regress, tests in test/sql, expected output in test/expected
```

回归测试从不调用真实 API。想体验真实效果，可 `SET jev.api_key` 后运行任意查询。

发布步骤参见 [CONTRIBUTING.md](CONTRIBUTING.md) 与 [docs/PUBLISHING.md](docs/PUBLISHING.md)。

## 许可证

[PostgreSQL 许可证](LICENSE)（PostgreSQL License）。Jev 与 TypeSafe 是其各自所有者的商标；
本项目与 TypeSafe 并无隶属关系。
