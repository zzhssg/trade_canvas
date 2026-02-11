---
title: 第5关：从 factor_slices 到 world_frame，讲透读模型一致性
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第5关：从 factor_slices 到 world_frame，讲透读模型一致性

前几关你学的是“怎么算”。  
这一关讲“怎么算完以后，怎么读才不乱”。

因为现实里最常见的问题不是算法错，而是：

- 因子已经推进到 A 时刻；
- 叠加图还停在 B 时刻；
- 前端把 A+B 拼到一起展示，用户看到一幅“物理上不存在的世界”。

trade_canvas 这套读链路，就是专门防这种“拼接幻觉”的。

---

## 0. 先给一句总纲

读模型一致性的核心不是“读得快”，而是：

**同一个响应里，所有视图必须指向同一根 candle（同一 `candle_id`）。**

只要这条守住，前端看到的就是一个真实时刻的快照；  
守不住，就宁可报 409，不给假画面。

---

## 1. 三层读模型：factor、draw、world

这套读取是分层的：

1. **FactorReadService**：读因子切片（history/head），并控制 freshness。
2. **DrawReadService**：读 overlay 增量（cursor patch），并做 overlay 完整性校验。
3. **WorldReadService**：把 factor + draw 合并成“世界帧”，再做最终一致性门禁。

你可以理解为：  
前两层各自保证“我这条链尽量正确”，第三层保证“合起来仍然同一时空”。

---

## 2. 第一层：FactorReadService 的职责不是拼数据，而是管“口径是否新鲜”

`FactorReadService.read_slices` 做的事：

- 先对齐时间（aligned_time）；
- 再调用 `read_factor_slices_with_freshness`；
- 按模式决定是否隐式追平 ledger。

关键策略：

- 非 strict：自动尝试 `ingest_closed`，尽量帮你追平。
- strict：如果 `factor_head < aligned_time`，直接 409（`ledger_out_of_sync:factor`）。

设计含义：  
读接口不是“盲读 DB”，而是“带一致性语义的读取”。

---

## 3. 第二层：DrawReadService 的职责是“增量可读 + 叠加完整性”

`DrawReadService.read_delta` 关键动作有三组：

1. **对齐 to_time**
   - 指定 `at_time` 就按 floor_time 对齐；
   - 不指定就按 store/overlay head 推一个可读时间。

2. **守 overlay head**
   - overlay 不到位，直接 409（`ledger_out_of_sync:overlay`）。

3. **首包完整性校验（cursor=0）**
   - 调 `evaluate_overlay_integrity` 对拍 factor slices 与 latest defs；
   - 不一致时拒绝返回，要求先 repair。

这说明 draw 侧不是“能给 patch 就给 patch”，而是“先保证 patch 站得住”。

---

## 4. 第三层：WorldReadService 的关键一刀——强制 `candle_id` 一致

`WorldReadService` 会读两份数据：

- `factor_slices`
- `draw_state`（draw delta）

然后走 `_require_matching_candle_id`：

- 期望 `factor_slices.candle_id == draw_state.to_candle_id == f"{series_id}:{aligned_time}"`；
- 任一不等，直接抛 `ledger_out_of_sync`（409）。

这是全链最关键的“时空一致性闸门”。  
很多系统只校验“都有数据”，但这里校验“是不是同一根 candle 的数据”。

---

## 5. 两种 world 读取方式：live 帧 vs 指定时刻帧

### `read_frame_live`

- 取 market 与 overlay 的 head 较小值；
- 再 floor 到有效 candle；
- 构建当前可读世界帧。

本质：给你“当前最安全的公共交集时刻”。

### `read_frame_at_time`

- 直接按你给的 `at_time` 对齐；
- 构建该时刻世界帧。

本质：给你“历史定点回看”。

两者都复用同一个一致性闸门，不会因为入口不同就放松标准。

---

## 6. world delta 轮询：为什么要 cursor 化

`poll_delta(after_id)` 的逻辑是：

- 先读 draw delta 的 next cursor；
- 没有新版本就返回空 records；
- 有新版本才返回一条包含 draw_delta + factor_slices 的 world record。

这带来三个工程收益：

- 前端增量拉取，不用每次全量刷。
- “有变化才有记录”，天然节流。
- 游标是显式协议，断线重连可恢复。

---

## 7. 这套设计背后的工程原则

- **Fail closed**：不一致时拒绝服务，不返回拼接假象。
- **Alignment first**：先对齐时间，再讨论数据内容。
- **Composable reads**：先分域读取，再统一闸门合并。
- **Cursor over snapshot spam**：用增量协议控制读压与状态同步。

这就是“读模型工程化”，不只是写个 GET 接口。

---

## 8. 给初学者的理解捷径

把它想成摄像机系统：

- factor 是 A 机位；
- draw 是 B 机位；
- world 是导演台输出。

导演台的硬规则是：  
两台机位必须是同一时间码，否则不上屏。

`candle_id` 就是时间码。

---

## 9. 代码锚点（按阅读顺序）

- `backend/app/read_models/factor_read_service.py`
- `backend/app/factor_read_freshness.py`
- `backend/app/read_models/draw_read_service.py`
- `backend/app/read_models/world_read_service.py`
- `backend/app/factor_slices_service.py`
- `backend/app/factor_slice_plugins.py`

---

## 10. 过关自测

1. 为什么 world 层还要再做一次 `candle_id` 一致性校验？  
2. 非 strict 与 strict 在 factor 读取上有什么语义差异？  
3. 为什么 draw 首包（cursor=0）需要完整性校验而不是直接放行？  
4. `poll_delta` 为什么“无变化返回空”反而是好设计？  
5. 如果前端出现“图线和信号错位”，你会先查哪一层？

如果这 5 题你能顺着讲，读模型一致性这关就过了。
