# Source of Truth（真源）

本文件用于明确“唯一权威位置”，避免同一事实在多处漂移。

## 约定
- 如果某个 schema/契约/关键常量存在唯一权威位置：在这里登记，并在其它文档中引用它。
- 若权威位置发生迁移：必须同时更新这里和相关引用文档。

## 真源清单（待补全）

| 主题 | 真源位置（代码/文档） | 说明 |
|---|---|---|
| CandleClosed / candle_id / series_id | `docs/core/market-kline-sync.md` | 市场 K 线同步的稳定主键与字段最小集合（闭合 K 为权威输入） |
| 市场 K 线同步协议（HTTP + WS） | `docs/core/market-kline-sync.md` | Whitelist 实时 + 非白名单按需补齐的最小 v1 设计 |
| Whitelist（series_id 列表） | `backend/config/market_whitelist.json` | 白名单内币种需要保证实时性；可作为 ingest 常驻的输入 |
| backtest（freqtrade bridge） | `docs/core/backtest.md` | 策略列表、回测运行、stdout/stderr 输出与最小配置口径 |
| 因子数据外壳（history/head/meta） | `docs/core/contracts/factor_v1.md` | 因子输出的统一外壳 + 冷热语义与不变量 |
| 因子拓扑（depends_on）与调度 | `docs/core/contracts/factor_graph_v1.md` | 拓扑闭包、稳定拓扑序、deps_snapshot 只读约束 |
| 因子真源账本（冷热） | `docs/core/contracts/factor_ledger_v1.md` | 冷事件流定点切片 + 热快照定点查询 + 幂等/可复现门禁 |
| 二级增量账本（delta） | `docs/core/contracts/delta_ledger_v1.md` | live/replay 共用的增量数据源（避免各处重算漂移） |
| Overlay / chart 指令 | `docs/core/contracts/overlay_v1.md` | 绘图增量（points + overlay_events + cursor） |
| Adapter 边界契约 | `docs/core/contracts/strategy_v1.md` | 策略消费快照与 fail-safe（candle_id 对齐门禁） |
