---
title: 后端结构性重构-读写边界与路由拆分
status: 待验收
owner: codex
created: 2026-02-11
updated: 2026-02-11
---

## 背景

当前后端主链路已收敛，但仍存在三类结构性问题：
1) draw 读请求在非 strict 下会隐式重建 overlay，读写边界不清；
2) `market_meta_routes.py` 过胖，健康/调试/榜单/SSE 职责混杂；
3) `dev_routes.py` 直接调用 `WorktreeManager._read_index()` 私有方法，封装破口。

在完成上述改造后，继续发现 factor 写路径仍残留 `processor`/`plugin` 双口径命名，影响架构语义一致性与后续扩展可读性。

## 目标 / 非目标

### 目标
- 读链路默认只读：发现 overlay 不一致时返回 `409 ledger_out_of_sync:overlay`。
- 引入显式 repair 入口：`POST /api/dev/repair/overlay`，受 `TRADE_CANVAS_ENABLE_READ_REPAIR_API` 控制（默认关闭）。
- 拆分市场 meta 路由，按健康/调试/榜单三组职责落盘。
- 修复 worktree 管理器封装边界，避免路由访问私有方法。
- 收敛 factor 写路径术语到 `tick_plugin`，并保留兼容别名避免一次性切断存量调用。

### 非目标
- 本轮不改动核心因子算法（pivot/pen/zhongshu/anchor 规则不变）。
- 本轮不改 API 主路径语义（`/api/draw/delta` 仍为 draw 主入口）。

## 方案概述

1. **显式 repair 服务**
   - 新增 `ReadRepairService`，执行 `refresh_series_sync` + `overlay.reset_series` + `overlay.ingest_closed`。
   - 校验 `factor_head`/`overlay_head` 与 `aligned_time` 对齐，失败返回 409。

2. **draw 读链路去隐式自愈**
   - `DrawReadService` 在完整性检查失败时不再内联重建，统一抛 `draw_read.ledger_out_of_sync.overlay`。

3. **路由职责拆分**
   - `market_health_routes.py`（whitelist + health）
   - `market_debug_routes.py`（debug ingest_state + series_health）
   - `market_top_markets_routes.py`（top_markets + stream）
   - `market_meta_routes.py` 保留为组合注册壳。

4. **封装修复**
   - `WorktreeManager` 新增公开 `read_index()`。
   - `dev_routes.py` 改为调用公开方法。

## E2E 用户故事（门禁）

- 角色：研究员。
- 目标：读接口保持只读，账本不一致时显式修复后恢复一致。
- 流程：
  1) ingest 固定 candle 序列；
  2) 人工删除 `anchor.current` overlay 指令；
  3) `GET /api/draw/delta` 返回 409；
  4) `POST /api/dev/repair/overlay`（开关开启）返回 200；
  5) 再次 `GET /api/draw/delta` 返回 200 且包含 `anchor.current`。
- 关键断言：
  - 失败前错误码必须是 `ledger_out_of_sync:overlay`；
  - repair 后 `active_ids` 恢复；
  - repair 响应包含 `overlay.reset_series` 与 `overlay.ingest_closed` 步骤。

## 里程碑

- M1：新增 repair service + repair route + runtime flag。
- M2：draw 去隐式 rebuild，读请求仅返回一致/不一致结果。
- M3：market meta 路由拆分 + worktree 封装修复。
- M4：回归测试与文档同步。
- M5：factor processor -> tick plugin 命名迁移（兼容模式）。
- M6：ws_hub 职责收敛（目标选择、gap 判定、批量/单条投递统一）。
- M7：overlay renderer 拆模块（contract/bucketing/renderers/facade）。
- M8：overlay orchestrator 读写拆分 + factor→overlay 一致性集成测试。
- M9：overlay orchestrator 依赖倒置（reader/writer 可注入）+ 编排测试。

## 任务拆解
- [x] 新增 `ReadRepairService` 与 `repair_routes.py`，接入 container/dependencies。
- [x] 新增 `TRADE_CANVAS_ENABLE_READ_REPAIR_API` 运行时开关。
- [x] 修改 `DrawReadService`：完整性失败改为 409，不再写操作。
- [x] 拆分 market meta 路由并保留组合注册层。
- [x] `WorktreeManager.read_index()` 公共化并替换 `dev_routes` 私有访问。
- [x] 补齐/更新回归测试并跑门禁。
- [x] 同步 core 文档并通过 `doc_audit`。
- [x] `factor_manifest` 主字段切换为 `tick_plugins`，保留 `processors` 兼容只读别名与入参别名。
- [x] `factor_default_components` 使用 `tick_plugin_builder` 术语，保留 `processor_builder` 只读兼容属性。
- [x] 因子实现与装配测试更新为 tick plugin 术语，`pytest -q` 全量通过。
- [x] core 契约文档同步命名迁移（plugin 口径）。
- [x] `ws_hub` 提取目标收集/间隙判定/消息发送辅助方法，消除 `publish_closed` 与 `publish_closed_batch` 重复逻辑。
- [x] 新增 `test_ws_hub_delivery.py` 覆盖批量投递、gap 回补、单条投递兼容语义。
- [x] `overlay_renderer_plugins.py` 拆分为 contract/bucketing/marker/pen/structure 子模块，并保留 facade 兼容导出。
- [x] `test_overlay_renderer_plugins.py` 通过，验证拆分后注册、bucket、渲染语义保持不变。
- [x] `overlay_orchestrator.py` 内部拆分 `OverlayIngestReader` / `OverlayInstructionWriter`，收敛窗口读取与落库去重职责。
- [x] 新增 `test_overlay_orchestrator_integration.py`，覆盖 factor 事件到 overlay 指令的主链路一致性与幂等写入。
- [x] `OverlayOrchestrator` 支持注入 reader/writer 依赖，避免编排层硬绑定实现细节。
- [x] 新增 `test_overlay_orchestrator_composition.py`，覆盖编排层调用契约与 ingest disabled 早退语义。

## 风险与回滚

- 风险：
  - draw 自愈行为移除后，历史依赖“自动修复”的调用路径会直接收到 409。
  - factor 术语迁移若直接改签名，可能影响存量测试与调用方。
- 回滚策略：
  1) 功能熔断：`TRADE_CANVAS_ENABLE_READ_REPAIR_API=0` 关闭 repair 入口；
  2) 提交回滚：按里程碑提交执行 `git revert <sha>`；
  3) 路由拆分异常时，可暂时回退到旧 `market_meta_routes` 聚合实现。
  4) 命名迁移异常时，优先使用兼容别名（`processors`/`ProcessorSpec`）兜底后再逐步清理。

## 验收标准

- `pytest -q backend/tests/test_draw_delta_api.py backend/tests/test_read_repair_api.py`
- `pytest -q backend/tests/test_market_data_services.py backend/tests/test_worktree_manager.py`
- `pytest -q backend/tests/test_app_state_boundary.py backend/tests/test_backend_architecture_flags.py`
- `pytest -q`
- `bash docs/scripts/doc_audit.sh`

## 变更记录
- 2026-02-11: 创建计划（草稿）。
- 2026-02-11: 进入开发中，完成 repair 服务/路由、draw 读边界收紧、market meta 拆分与封装修复。
- 2026-02-11: 门禁通过（`pytest -q`、`bash docs/scripts/doc_audit.sh`），状态推进为待验收。
- 2026-02-11: 继续开发，完成 factor processor -> tick plugin 命名迁移（含兼容别名），全量测试通过。
- 2026-02-11: 继续开发，完成 ws_hub 投递职责收敛与回归测试补齐（delivery path 5 条测试通过）。
- 2026-02-11: 继续开发，完成 overlay renderer 模块拆分（facade 兼容），全量测试通过。
- 2026-02-11: 继续开发，完成 overlay orchestrator 读写拆分与一致性集成测试补齐，全量测试通过。
- 2026-02-11: 继续开发，完成 overlay orchestrator 依赖注入与编排测试补齐，全量测试通过。
