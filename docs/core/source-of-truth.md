---
title: Source of Truth（真源总表）
status: done
created: 2026-02-02
updated: 2026-02-14
---

# Source of Truth（真源总表）

本表用于明确“唯一权威位置”，避免同一事实在多处漂移。

维护规则：
1. 真源迁移时，必须同轮更新本表。
2. 非真源文档只能引用，不复制关键规则。
3. 核心链路变更后必须跑 `bash docs/scripts/doc_audit.sh`。

## 真源清单

| 主题 | 真源位置 | 说明 |
|---|---|---|
| 后端架构总览 | `docs/core/architecture.md` | 系统分层、职责边界、扩展策略 |
| 后端链路拆解 | `docs/core/backend-chain-breakdown.md` | 启动/写入/读取/回放的代码级路径 |
| 市场 K 线同步 | `docs/core/market-kline-sync.md` | closed/forming 语义、WS/回补/derived 策略 |
| 因子模块化 | `docs/core/factor-modular-architecture.md` | factor 写读链路、插件接入面 |
| Backtest 链路 | `docs/core/backtest.md` | backtest 分层、开关、失败语义 |
| API v1 总入口 | `docs/core/api/v1/README.md` | 所有 HTTP/WS 文档索引与门禁格式 |
| 契约总入口 | `docs/core/contracts/README.md` | 契约索引与版本化文档入口 |
| factor 外壳契约 | `docs/core/contracts/factor_v1.md` | history/head/meta 统一外壳 |
| factor ledger 契约 | `docs/core/contracts/factor_ledger_v1.md` | 冷热账本与切片读取约束 |
| draw delta 契约 | `docs/core/contracts/draw_delta_v1.md` | 图形增量协议（cursor + patch） |
| world state/delta 契约 | `docs/core/contracts/world_state_v1.md` / `docs/core/contracts/world_delta_v1.md` | 世界态聚合与增量轮询语义 |
| replay package 契约 | `docs/core/contracts/replay_package_v1.md` | replay 打包接口与窗口语义 |
| 市场榜单契约 | `docs/core/contracts/market_list_v1.md` | top markets HTTP/SSE 契约 |
| 配置真源（代码） | `backend/app/core/flags.py` / `backend/app/runtime/flags.py` | env 解析工具 + RuntimeFlags 唯一实现 |
| DI 装配真源（代码） | `backend/app/bootstrap/container.py` | 所有核心依赖的启动装配入口 |
| 写链路真源（代码） | `backend/app/pipelines/ingest_pipeline.py` | candles->factor->overlay 单路径编排 |
| 读修复入口（代码） | `backend/app/routes/repair.py` / `backend/app/read_models/repair_service.py` | 显式 repair（默认关闭，受 `TRADE_CANVAS_ENABLE_READ_REPAIR_API` 控制） |

## 非真源文档处理

- 历史说明、迁移日志、踩坑记录应放在 `docs/经验/` 或 `docs/复盘/`。
- 若保留在 `docs/core/`，必须明确标注 `status: deprecated` 且给出替代入口。
