# 不用向量索引，Postgres 也能做语义过滤：pg-jev 上手

> 原文：[不用向量索引，Postgres 也能做语义过滤：pg-jev 上手](https://mp.weixin.qq.com/s/FG9c3NCcbVz-6fhWhTMiug) · 微信公众号「AI工程化」 · 2026-10-04
>
> 中文原创文章，经非官方快照收录，仅作社区学习用途；版权归原作者所有。项目主页：[github.com/realZachi/pg-jev](https://github.com/realZachi/pg-jev)。

传统 SQL 的 WHERE 只能处理精确条件。 `age > 40` 没问题，但像"这封邮件是不是在威胁取消订阅"就写不成一行 SQL。常规解法是把行搬到应用层，调模型，解析输出，再把结果写回。

pg-jev 把这个流程压缩进了 Postgres。

它是个开源扩展，把 TypeSafe 的 Jev 包装成 SQL 函数。Jev 不生成文本，只返回一组选项上的校准概率。不需要向量列，不需要 embedding index。

四个函数，各管一摊：

```sql
-- 当 WHERE 条件用
SELECT * FROM people WHERE jev(people, 'the name is European');

-- 返回概率
SELECT subject, jev_prob(tickets, 'the customer is angry') AS p
FROM tickets ORDER BY p DESC LIMIT 20;

-- 从给定选项里选一个
SELECT jev_choice(tickets, 'which team should handle this?',
ARRAY['billing', 'technical', 'security', 'sales']) AS team, count(*)
FROM tickets GROUP BY 1;

-- 在有序等级上打分
SELECT name, jev_score(products, 'how luxurious is this product?',
ARRAY['budget', 'mid-range', 'premium', 'luxury']) AS luxury
FROM products ORDER BY luxury DESC;
```
`jev()` 是普通布尔函数，可以跟 `AND age > 40`、join、`GROUP BY`、`LIMIT`、`ORDER BY` 随意组合。

机制不复杂：行按每批 20 条打包，连同问题发给 Jev，返回结果直接参与 SQL 过滤排序。答案缓存在当前会话里，重复跑、改阈值、按概率排序几乎免费。

实测数据：2000 行表，首次查询约 3.5 秒，100 个请求，约 296k input tokens，约 $0.012。第二次约 50 毫秒。同一会话里换新条件带 `LIMIT 3` ，约 0.6 秒。

## 几个需要注意的点

**全扫描设计。**
执行器问到的每一行都会发给 API。便宜的谓词先执行， `LIMIT` 会提前停，但它不是索引的替代品。 `jev.max_rows_per_statement` 可以设上限防止手滑。

**label-set drift。**
加一个合法选项，旧阈值全部失效。这些概率是条件概率——加一个标签，其他标签的概率都会变，即使模型和 prompt 没动。真正可部署的单元是模型、prompt、tokenizer、标签集和阈值一起版本化。

**跨后端不可移植。**
概率在不同模型或量化之间不能直接比。同一个问题在两个后端的分数可能差很多。Avi 回复说他正在做校准层。

**安装限制。**
需要 PostgreSQL 14-17、plpython3u 和 superuser。Supabase、Neon、RDS 这类托管服务不给 plpython3u，跑不了。Docker 是相对省事的路径。数据默认发给 TypeSafe API；如果数据不能出网， `jev.api_url` 可以指向本地兼容服务。

GitHub 仓库：https://github.com/realZachi/pg-jev
