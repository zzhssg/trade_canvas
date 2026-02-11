---
title: 第28关：从 SQLite 三库到 append-only，讲透数据库设计的取舍
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第28关：从 SQLite 三库到 append-only，讲透数据库设计的取舍

上一关你学了"用测试守住架构"。这一关解决一个更底层的问题：

**数据该怎么存，才能同时满足"写得快、读得准、查得到历史"？**

很多人做系统时，数据库设计只有一种思路：建一张表，有啥字段加啥列，改了就 UPDATE。

这在玩具项目里没问题。但在真实系统里，你很快会撞上三个矛盾：

1. K 线数据要紧凑高效，重复推送不能炸表；
2. 因子事件要完整保留历史，支持"定点切片"做可复现；
3. 覆盖层指令频繁变化，客户端要能增量同步。

这三种需求，用同一种写入策略根本搞不定。

想象一家超市的三种存储场景：

- **冷库**（存原材料）：牛奶到了就上架，过期的替换掉，货架上同一个位置永远只有一瓶——这是 CandleStore 的 upsert。
- **账本**（记流水）：每笔交易都要记，哪怕同一个客户买了两次同样的东西，也要分别记录——但同一张发票不能入账两次——这是 FactorStore 的 append-only。
- **货架标签**（展示信息）：价签经常换，但只有真正改了价格才换新标签，旧标签存档备查——这是 OverlayStore 的版本化写入。

---

## 0. 先给一句总纲

数据库设计的核心不是"用什么数据库"，而是"每种数据的写入策略和读取模式是什么"。

trade_canvas 用三个独立 SQLite 库，分别对应三种策略：

1. **CandleStore**：权威输入 → upsert 覆盖 → 存储紧凑
2. **FactorStore**：衍生事件 → append-only + 幂等去重 → 可复现
3. **OverlayStore**：展示指令 → 版本化 append-only + 内容去噪 → 增量同步

一个库一种策略，互不干扰。

---

## 1. 第一幕：CandleStore——冷库里的牛奶，到了就上架

入口在 `backend/app/store.py`。

`candles` 表的主键是 `(series_id, candle_time)`。写入用 `INSERT ... ON CONFLICT DO UPDATE`。

这意味着：

- 同一根 K 线（同品种、同时刻）永远只占一行；
- Binance WS 重复推送同一根 K 线，不会多出第二行；
- 新值直接覆盖旧值。

超市比喻：冷库货架上，同一个位置永远只放一瓶牛奶。新到的牛奶直接替换旧的，不会出现两瓶挤在一起的情况。

为什么不用 append-only？因为 K 线是"权威输入"——一旦闭合就是事实，不需要保留"这根 K 线被写了几次"的历史。而且每个品种每分钟一条，年数据量巨大，append-only 会让存储无意义膨胀。

---

## 2. 第二幕：FactorStore——账本里的流水，每笔都要记

入口在 `backend/app/factor_store.py`。

这个库最复杂，因为它要同时解决三个问题：

### 2.1 冷账本：factor_events（事件流）

表有唯一约束 `UNIQUE(series_id, factor_name, event_key)`，写入用 `ON CONFLICT DO NOTHING`。

这是"发票号"模式：

- 每个因子事件有一个稳定的 `event_key`（比如 `pivot:1000:major`）；
- 同一张"发票"不管提交几次，只入账一次；
- 但不同的事件必须全部保留。

超市比喻：账本里每笔交易都记，但同一张发票号不能重复入账。这样既保证了完整历史，又防止了重复记录。

### 2.2 热账本：factor_head_snapshots（头快照）

这张表更精妙。写入前会先查最新版本：

- 如果 `head_json` 内容没变，直接返回现有 `seq`，不追加新行；
- 只有内容真正变了，才 `seq + 1` 追加新版本。

超市比喻：收银台的"今日销售额"看板。只有数字真的变了才换新看板，不会每分钟都换一块写着同样数字的新看板。

### 2.3 进度指针：factor_series_state

简单的 upsert 表，只记录"我已经处理到哪个时刻"。

这不是真源数据，只是一个快速查询入口——就像账本封面上写的"截至第 X 页"，方便快速定位，但真正的数据在账本里面。

---

## 3. 第三幕：OverlayStore——货架标签，改了价才换

入口在 `backend/app/overlay_store.py` 和 `backend/app/overlay_ingest_writer.py`。

`overlay_instruction_versions` 表用 `version_id` 自增主键，没有唯一约束——同一个 `instruction_id` 允许有多个版本。

但写入时有一个关键的应用层去噪：`_is_latest_def_same(...)` 会比较最新版本的 `def_json`：

- 内容相同 → 跳过，不追加新版本；
- 内容不同 → 插入新行，`version_id` 自增。

超市比喻：货架上的价签。只有价格真的变了才换新标签，旧标签存档备查。如果每次巡检都换一张写着同样价格的新标签，档案柜很快就满了。

这个设计还有一个重要收益：客户端可以用 `version_id` 做增量同步游标。

```text
客户端："我上次同步到 version_id=100，之后有什么新的？"
服务端："version_id > 100 的有这 3 条变更，拿去。"
```

这比"每次全量拉取所有覆盖层"高效得多。

---

## 4. 第四幕：为什么是三个独立 SQLite 库，而不是一个？

很多人的第一反应是"一个数据库不就行了？"

答案是：职责隔离。

| 维度 | 合库 | 分库（现方案） |
| ---- | ---- | -------------- |
| 写入竞争 | K 线高频写入会阻塞因子查询 | 各库独立锁，互不干扰 |
| 备份粒度 | 只能整库备份 | 可以单独备份/清理某个库 |
| 生命周期 | 所有数据同生共死 | K 线可以独立裁剪，不影响因子 |
| 测试隔离 | 测试要准备所有表 | 单测只需要关心自己的库 |

超市比喻：冷库、账本、货架标签分开管理。你不会把牛奶和账本放在同一个冷库里——温度不对，而且盘点时互相干扰。

SQLite 的 WAL 模式下，每个库有独立的写锁。三库分离意味着 K 线写入不会阻塞因子读取，因子写入不会阻塞覆盖层查询。

---

## 5. 第五幕：三种幂等策略的对比

三个库用了三种不同的幂等实现，各有适用场景：

| 策略 | 实现 | 适用场景 | 代表 |
| ---- | ---- | -------- | ---- |
| 主键冲突覆盖 | `ON CONFLICT DO UPDATE` | 权威数据，只需最新值 | CandleStore |
| 唯一键忽略 | `ON CONFLICT DO NOTHING` | 事件流，同事件不重复 | FactorStore 事件 |
| 应用层比较 | 先读最新，内容相同则跳过 | 版本化数据，避免噪声版本 | OverlayStore / FactorStore 快照 |

第一种最简单，数据库层面就搞定了。第二种需要设计稳定的 `event_key`。第三种最灵活但也最贵——每次写入前要先读一次。

选哪种，取决于你的数据是"事实覆盖型"、"事件追加型"还是"版本演进型"。

---

## 6. 第六幕：读取模式决定索引设计

三个库的读取模式完全不同，索引也跟着不同：

**CandleStore**：时间范围扫描

- 最常用查询：`WHERE series_id = ? AND candle_time BETWEEN ? AND ?`
- 主键 `(series_id, candle_time)` 天然覆盖

**FactorStore**：多维切片

- 事件查询：`WHERE series_id = ? AND candle_time BETWEEN ? AND ?`，按 `id` 排序
- 快照查询：`WHERE series_id = ? AND factor_name = ? AND candle_time <= ?`，取 `seq` 最大

**OverlayStore**：版本游标 + 时间过滤

- 增量同步：`WHERE series_id = ? AND version_id > ? AND visible_time <= ?`
- 最新快照：子查询 `GROUP BY instruction_id` 取 `MAX(version_id)`

索引设计的铁律：**先确定读取模式，再设计索引。** 不是反过来。

---

## 7. 第七幕：进度指针为什么不是真源

FactorStore 和 OverlayStore 都有一张 `*_series_state` 表，记录 `head_time`。

这张表是 upsert 的，只存"我处理到哪了"。

为什么要单独一张表？因为判断"是否已处理到某时刻"是一个极高频操作。如果每次都去扫描事件表找 `MAX(candle_time)`，成本太高。

但它不是真源——真正的数据在事件表和快照表里。如果 `head_time` 和实际数据不一致（比如写入中途崩溃），系统会通过 `ledger_out_of_sync` 检测到，而不是默默返回错误数据。

超市比喻：账本封面写着"截至第 200 页"，但如果你翻开发现只写到第 198 页，你知道封面信息过时了——而不是假装第 199、200 页存在。

---

## 8. 这套设计背后的通用方法论

你可以把它抽象成一套"数据库设计决策树"：

1. **先问数据特性**：是权威输入、衍生事件、还是展示数据？
2. **再问写入语义**：覆盖型、追加型、还是版本型？
3. **然后问读取模式**：时间范围、定点切片、还是增量游标？
4. **最后问隔离需求**：写入频率差异大不大？生命周期一样吗？

回答完这四个问题，策略自然就出来了。不要一上来就想"用 MySQL 还是 PostgreSQL"——那是最后才考虑的事。

---

## 9. 代码锚点（建议顺读）

- `backend/app/store.py`（CandleStore：upsert 策略）
- `backend/app/factor_store.py`（FactorStore：混合策略）
- `backend/app/overlay_store.py`（OverlayStore：版本化策略）
- `backend/app/overlay_ingest_writer.py`（覆盖层写入去噪）
- `backend/tests/test_factor_head_store.py`（快照版本化验证）
- `backend/tests/test_overlay_orchestrator_integration.py`（覆盖层幂等验证）
- `backend/tests/test_ingest_pipeline.py`（写链路集成验证）

---

## 10. 过关自测

1. 为什么 CandleStore 用 upsert 而不是 append-only？
2. `event_key + ON CONFLICT DO NOTHING` 和 `主键 + ON CONFLICT DO UPDATE` 的语义差异是什么？
3. OverlayStore 的应用层去噪（比较 `def_json`）解决了什么问题？
4. 三库分离相比合库，在 SQLite WAL 模式下的核心收益是什么？
5. 进度指针（`head_time`）为什么不能作为真源？

如果这 5 题你能讲清楚，你已经从"会建表"进阶到"会根据数据特性设计存储策略"。
