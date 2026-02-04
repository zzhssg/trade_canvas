---
title: Replay OverlayPackage v1 MVP（window 增量 + checkpoint/diff + catalog_base/patch）
status: 开发中
owner:
created: 2026-02-04
updated: 2026-02-04
---

## 背景

现有 replay（`frontend/src/widgets/ChartView.tsx`）在 seek/回退时无法正确回滚 overlay 的 instruction catalog（只会单向 apply patch），导致“画面可能对但语义漂移”。

本 MVP 只工程化落地一条链路：**Overlay 的最小差值加载**（包 + window + 本地重建），并保持：
- `factor/history/head`：继续用 `GET /api/factor/slices?at_time=...` 点查（仅用户打开面板/调试时请求）。
- `world` 定点查询：继续用 `GET /api/frame/at_time` 做 fail-safe 对齐检查（不改变现有门禁）。

## 目标 / 非目标

### 目标（MVP）
- 后端提供一个可缓存、可复用、可按 window 增量拉取的 overlay replay package（覆盖最近 2000 根 closed candles）。
- 前端播放/拖动 K 线时：
  - K 线数据本地切片/增量更新（不全量重绘）。
  - overlay 按 **window 独立可重建** 的协议：`catalog_base + catalog_patch + checkpoint + diff` 应用（不每次请求全量指令/全量状态）。

### 非目标（MVP 不做）
- 不把 factor 做成随播放增量的 replay-package（后续迭代再做）。
- 不引入 trade_system 那套完整 FactorLedger/SlotDeltaLedger 落地（本次只做 overlay replay-package 的工程化落地，但为未来演进预留契约位）。

## 默认参数（本计划锁定）
- `window_candles=2000`
- `WINDOW_SIZE=500`
- `snapshot_interval=25`
- `preload_offset=0`
- polyline active 规则：最早点 `time <= 当前 candle_time` 即 active（避免频繁 add/remove）

## 方案概述（v1）

后端新增 `OverlayReplayPackage` 子系统（独立于现有 `/api/draw/delta`；旧的 `/api/overlay/delta` 已于 2026-02-04 移除）：
- `read-only`：只读探测缓存，miss 返回 `build_required`（不隐式重算）。
- `build`：显式创建构建任务，落盘缓存。
- `status`：轮询任务状态；可选首包（用于减少第一次进入 replay 的请求次数）。
- `window`：按 `WINDOW_SIZE=500` 切片返回指定 window，并携带：
  - `catalog_base`（window 起点的完整可用 catalog）
  - `catalog_patch`（window 内的增量版本）
  - `checkpoints + diffs`（用于从 window 起点重建任意 idx 的 `active_ids`）

前端在 replay 模式下：
- 先 `read-only`；若 `build_required` 展示 build 按钮（用户点击触发 `build`）。
- `status` 轮询到 done 后：
  - K 线使用首包/缓存数据本地切片 + `series.update` 优先（seek 大跳才 `setData`）。
  - overlay：按需拉取 window（并在接近窗口末端预取下一窗），用本地 `ReplayWindowStateCache` 从 checkpoint+diff 重建 `active_ids`，再从 `catalog_base + catalog_patch` 重建当下 catalog，增量更新图元。

## 里程碑

1) 落契约 + API 文档（不改现有链路）
2) 后端实现 replay-package（read-only/build/status/window + 磁盘缓存）
3) 前端接入（feature flag 回滚；seek 正确；window 缓存 + 预取）
4) 补齐后端回归测试 + Playwright E2E（纳入 `scripts/e2e_acceptance.sh`）

## 任务拆解（每步都可回滚）

- [ ] 新增契约与 API 文档：`docs/core/contracts/overlay_replay_protocol_v1.md`、`docs/core/api/v1/http_replay.md`
  - 验收：`bash docs/scripts/doc_audit.sh`
  - 回滚：删除新增文档
- [ ] 后端新增 endpoints + 磁盘缓存构建（开关默认关闭）
  - 验收：`pytest -q -k replay_overlay_package_v1`
  - 回滚：`TRADE_CANVAS_ENABLE_REPLAY_PACKAGE=0` 或 `git revert`
- [ ] 前端接入 hook + window 缓存 + seek 正确性（开关默认关闭）
  - 验收：`cd frontend && npm run build`
  - 回滚：`VITE_ENABLE_REPLAY_PACKAGE_V1=0`
- [ ] E2E：新增 replay 用例（只读优先 + window 增量 + seek 不重复拉取）
  - 验收：`E2E_PLAN_DOC=docs/plan/2026-02-04-replay-overlay-package-v1-mvp.md bash scripts/e2e_acceptance.sh`
  - 回滚：移除 spec / 关闭开关

## 风险与回滚

### 风险
- seek 正确性：若 catalog 无法在 t 时刻重建，将出现“向后 seek 漂移”（本计划通过 window 独立可重建规避）。
- 缓存失效：cache_key 不稳定会导致重复构建或读到错误包（必须可复现）。

### 回滚
- 后端：`TRADE_CANVAS_ENABLE_REPLAY_PACKAGE=0`（新 endpoints 返回 404）
- 前端：`VITE_ENABLE_REPLAY_PACKAGE_V1=0`（回退到现有简易 replay）

## 验收标准（MVP）
- 包的读路径只读：read-only miss 不隐式重算，返回 build_required。
- window 独立可重建：同一 window 内任意 idx（含向后 seek）能正确重建 `active_ids` 与 catalog（至少对 pivot markers + pen polyline 可复现）。
- 请求增量：同一 window 内多次 seek 不重复请求该 window；接近末端触发预取下一窗。
- fail-safe 不变：`GET /api/frame/at_time` 仍可用于对拍；不改变 `ledger_out_of_sync` 语义。

## E2E 用户故事（门禁）

### Persona / Goal
- Persona：研究员
- Goal：在 Replay 页面回放最近 2000 根 K，反复 seek（含向后）并确认 overlay 不漂移，同时网络请求保持 window 增量。

### Entry / Exit
- Entry：通过 HTTP ingest 写入固定 2100 根 closed candles（保证可取尾部 2000 根），然后打开 `/replay`。
- Exit：完成 build（若需要）后，UI 可播放/可 seek；网络层满足 “只读优先 + window 增量”；关键断言通过。

### Concrete Scenario（具体数值）
- series_id：`binance:futures:BTC/USDT:1m`
- candle_time：从 `60` 开始递增到 `60*2100`
- seek 点（idx）：`10 → 300 → 20`（同一 window 内向后 seek 必须正确）

### Main Flow（步骤 + 断言）
1) 打开 `/replay`
   - 断言：出现 chart canvas；发生 `read-only` 请求
2) 若返回 build_required，点击 Build
   - 断言：发生 `build` + `status` 轮询直到 done
3) 在同一 window 内多次 seek（含向后）
   - 断言：`/window` 请求次数不随 seek 次数线性增长（命中缓存）；overlay 计数（例如 pivot/pen 点数）稳定且不会“越 seek 越多”
4) seek 到 window 末端附近
   - 断言：触发下一窗预取（出现下一窗的 `/window` 请求）

### Verification Commands（证据）
- `pytest -q -k replay_overlay_package_v1`
- `cd frontend && npm run build`
- `E2E_BACKEND_PORT=18080 E2E_FRONTEND_PORT=15180 E2E_PLAN_DOC=docs/plan/2026-02-04-replay-overlay-package-v1-mvp.md bash scripts/e2e_acceptance.sh`

## 变更记录
- 2026-02-04: 创建（开发中）
