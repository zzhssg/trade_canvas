---
title: 复盘：factor 逻辑哈希门禁与重建入口上线过程
status: 已完成
created: 2026-02-07
updated: 2026-02-07
---

# 复盘：factor 逻辑哈希门禁与重建入口上线过程

## 背景

本轮改动围绕 factor 产物有效性：
- 新增 `logic_hash` 并在读路径做 fail-safe（`409 stale_factor_logic_hash:*`）。
- 新增 `POST /api/factor/rebuild` 用于按 `series_id` 重建 factor/overlay。

主要文件：
- `backend/app/factor_store.py`
- `backend/app/factor_orchestrator.py`
- `backend/app/main.py`
- `backend/app/overlay_store.py`
- `backend/app/schemas.py`

## 具体错误

1) 文档门禁首次失败（`api_docs_audit`）
- 现象：`docs/scripts/doc_audit.sh` 失败，报 `POST /api/factor/rebuild` 缺少 `### 语义/说明`，且 request body endpoint 需要 request+response 两个 json code block。
- 证据：审计输出中明确指出 `docs/core/api/v1/http_factor.md` 的结构缺失。

2) 发布前没有先按“高风险能力”清单核对 kill-switch
- 现象：`/api/factor/rebuild` 属于高风险写路径能力，初版没有显式开关。
- 影响：虽然接口可用，但在生产/共享环境中缺乏快速熔断手段。

## 影响与代价

- 文档审计失败导致验收链路被阻断，增加一次返工。
- 高风险接口缺少开关会提高误触风险与回滚成本。

## 根因

- 先做了接口实现和测试，后补 API 文档时未完全按 `api_docs_audit` 的固定模板落盘。
- 对“高风险新能力默认 kill-switch”执行不够前置，检查顺序靠后。

## 如何避免（检查清单）

### 开发前
- [ ] 识别是否属于“高风险写能力”（删除/重建/回放重算）。
- [ ] 若是高风险，先定义 `TRADE_CANVAS_ENABLE_*` 开关与默认值。
- [ ] 在 plan 中写清“可回滚路径 + 验收门禁”。

### 开发中
- [ ] 新增 API 同步补齐 `docs/core/api/v1/*`：`curl`、request json、response json、语义小节。
- [ ] 每新增 endpoint 后立即本地跑一次 `bash docs/scripts/doc_audit.sh`。
- [ ] 读路径 fail-safe 错误码提前固定并补测试。

### 验收时
- [ ] `pytest -q`、`cd frontend && npm run build`、`bash docs/scripts/doc_audit.sh` 全绿再宣称完成。
- [ ] 汇报中明确 Doc Impact 和受影响文档路径。
- [ ] 对高风险能力补一句“如何一键禁用”。

## 关联

- 验证命令：
  - `pytest -q`
  - `cd frontend && npm run build`
  - `bash docs/scripts/doc_audit.sh`
- 关联文件：见本文“背景”章节。
