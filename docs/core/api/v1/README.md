---
title: API v1（endpoint 清单 + 示例）
status: draft
created: 2026-02-03
updated: 2026-02-07
---

# API v1（endpoint 清单 + 示例）

本目录用于维护 **版本化的 endpoints 清单 + 可执行示例**，作为：
- 研发前“先看存量 API”入口
- 研发后“文档是否完整”门禁的一部分（见 `docs/scripts/api_docs_audit.sh`）

覆盖范围（v1）：
- HTTP：`/api/**`
- WebSocket：`/ws/**`
- SSE：仍按 HTTP GET 处理（例如 `GET /api/market/top_markets/stream`）

## 约定（强制）

### 1) 章节标题（门禁依赖）

- HTTP：`## <METHOD> <PATH>`（例：`## GET /api/market/candles`）
- WS：`## WS <PATH>`（例：`## WS /ws/market`）

### 2) 每个 endpoint 必须包含（门禁依赖）

- 至少 1 个 `bash` 代码块（必须包含可复制执行的 `curl` / `wscat` / `websocat` 示例）
- 至少 1 个 `json` 代码块（响应示例）
- 若该 endpoint 有 request body：至少 2 个 `json` 代码块（request + response）
- `### 语义`（或 `### 说明`）小节：写清对齐/游标/失败语义等关键约束

### 3) Base URL（本地默认）

- HTTP：`http://127.0.0.1:8000`
- WS：`ws://127.0.0.1:8000`

> 说明：如你的 shell 配了代理（`http_proxy/https_proxy`），建议 `curl` 都加 `--noproxy '*'`，避免访问 `localhost/127.0.0.1` 卡住。

## 目录索引

- Market（HTTP + SSE）：`docs/core/api/v1/http_market.md`
- Plot（HTTP）：`docs/core/api/v1/http_plot.md`
- Overlay（HTTP）：`docs/core/api/v1/http_overlay.md`
- Draw（HTTP）：`docs/core/api/v1/http_draw.md`
- Factor（HTTP）：`docs/core/api/v1/http_factor.md`
- World（HTTP）：`docs/core/api/v1/http_world.md`
- Backtest（HTTP）：`docs/core/api/v1/http_backtest.md`
- Dev（HTTP）：`docs/core/api/v1/http_dev.md`
- Market WS：`docs/core/api/v1/ws_market.md`
- Debug WS：`docs/core/api/v1/ws_debug.md`
