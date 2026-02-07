---
title: API v1 · Dev（HTTP）
status: draft
created: 2026-02-07
updated: 2026-02-07
---

# API v1 · Dev（HTTP）

## GET /api/dev/worktrees

### 语义

- 列出本机已登记的 worktree（含 metadata + services 状态）。
- 用于 dev panel/脚本快速发现可用 worktree 与服务端口。

### 示例（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/dev/worktrees"
```

### 示例响应（json）

```json
{
  "worktrees": [
    {
      "id": "8f05",
      "path": "/Users/rick/.codex/worktrees/8f05/trade_canvas",
      "branch": "codex/anchor-zhongshu",
      "commit": "c0ffee1",
      "is_detached": false,
      "is_main": false,
      "metadata": {
        "description": "Anchor + Zhongshu incremental draw/delta",
        "plan_path": "docs/plan/2026-02-06-anchor-zhongshu-draw-delta-incremental.md",
        "created_at": "2026-02-06T19:10:00Z",
        "owner": "rick",
        "ports": {"backend_port": 18080, "frontend_port": 15180}
      },
      "services": {
        "backend": {"running": true, "port": 18080, "pid": 30123, "url": "http://127.0.0.1:18080"},
        "frontend": {"running": true, "port": 15180, "pid": 30124, "url": "http://127.0.0.1:15180"}
      }
    }
  ]
}
```

## GET /api/dev/worktrees/{worktree_id}

### 语义

- 查询指定 worktree 的详细信息。
- 若 worktree 不存在，返回 404 + `detail=worktree_not_found`。

### 示例（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/dev/worktrees/8f05"
```

### 示例响应（json）

```json
{
  "id": "8f05",
  "path": "/Users/rick/.codex/worktrees/8f05/trade_canvas",
  "branch": "codex/anchor-zhongshu",
  "commit": "c0ffee1",
  "is_detached": false,
  "is_main": false,
  "metadata": {
    "description": "Anchor + Zhongshu incremental draw/delta",
    "plan_path": "docs/plan/2026-02-06-anchor-zhongshu-draw-delta-incremental.md",
    "created_at": "2026-02-06T19:10:00Z",
    "owner": "rick",
    "ports": {"backend_port": 18080, "frontend_port": 15180}
  },
  "services": {
    "backend": {"running": true, "port": 18080, "pid": 30123, "url": "http://127.0.0.1:18080"},
    "frontend": {"running": true, "port": 15180, "pid": 30124, "url": "http://127.0.0.1:15180"}
  }
}
```

## POST /api/dev/worktrees

### 语义

- 创建新的 worktree（默认基于 `base_branch=main`），并写入 metadata。
- `description` 至少 20 字符；失败时 `ok=false` 并返回 `error`。

### 示例请求（curl）

```bash
curl --noproxy '*' -sS -X POST \
  "http://127.0.0.1:8000/api/dev/worktrees" \
  -H 'content-type: application/json' \
  -d '{
    "branch": "codex/anchor-zhongshu",
    "description": "Anchor + Zhongshu incremental draw/delta",
    "plan_path": "docs/plan/2026-02-06-anchor-zhongshu-draw-delta-incremental.md",
    "base_branch": "main"
  }'
```

### 示例请求体（json）

```json
{
  "branch": "codex/anchor-zhongshu",
  "description": "Anchor + Zhongshu incremental draw/delta",
  "plan_path": "docs/plan/2026-02-06-anchor-zhongshu-draw-delta-incremental.md",
  "base_branch": "main"
}
```

### 示例响应（json）

```json
{
  "ok": true,
  "worktree": {
    "id": "8f05",
    "path": "/Users/rick/.codex/worktrees/8f05/trade_canvas",
    "branch": "codex/anchor-zhongshu",
    "commit": "c0ffee1",
    "is_detached": false,
    "is_main": false,
    "metadata": {
      "description": "Anchor + Zhongshu incremental draw/delta",
      "plan_path": "docs/plan/2026-02-06-anchor-zhongshu-draw-delta-incremental.md",
      "created_at": "2026-02-06T19:10:00Z",
      "owner": "rick",
      "ports": {"backend_port": 18080, "frontend_port": 15180}
    },
    "services": null
  }
}
```

## POST /api/dev/worktrees/{worktree_id}/start

### 语义

- 启动该 worktree 的后端/前端服务。
- `backend_port`/`frontend_port` 可选；不传则按系统分配。
- 失败时 `ok=false` 并返回 `error`。

### 示例请求（curl）

```bash
curl --noproxy '*' -sS -X POST \
  "http://127.0.0.1:8000/api/dev/worktrees/8f05/start" \
  -H 'content-type: application/json' \
  -d '{
    "backend_port": 18080,
    "frontend_port": 15180
  }'
```

### 示例请求体（json）

```json
{
  "backend_port": 18080,
  "frontend_port": 15180
}
```

### 示例响应（json）

```json
{
  "ok": true,
  "services": {
    "backend": {"running": true, "port": 18080, "pid": 30123, "url": "http://127.0.0.1:18080"},
    "frontend": {"running": true, "port": 15180, "pid": 30124, "url": "http://127.0.0.1:15180"}
  }
}
```

## POST /api/dev/worktrees/{worktree_id}/stop

### 语义

- 停止该 worktree 的后端/前端服务（若未运行则返回 ok=false 或 ok=true 由实现决定）。

### 示例（curl）

```bash
curl --noproxy '*' -sS -X POST \
  "http://127.0.0.1:8000/api/dev/worktrees/8f05/stop"
```

### 示例响应（json）

```json
{
  "ok": true
}
```

## DELETE /api/dev/worktrees/{worktree_id}

### 语义

- 删除 worktree，并归档 metadata。
- `force=true` 表示强制删除；失败时 `ok=false` 并返回 `error`。

### 示例请求（curl）

```bash
curl --noproxy '*' -sS -X DELETE \
  "http://127.0.0.1:8000/api/dev/worktrees/8f05" \
  -H 'content-type: application/json' \
  -d '{"force": false}'
```

### 示例请求体（json）

```json
{
  "force": false
}
```

### 示例响应（json）

```json
{
  "ok": true
}
```

## GET /api/dev/ports/allocate

### 语义

- 申请一对空闲端口（backend + frontend）。
- 仅用于 dev 工具，不会修改 worktree metadata。

### 示例（curl）

```bash
curl --noproxy '*' -sS \
  "http://127.0.0.1:8000/api/dev/ports/allocate"
```

### 示例响应（json）

```json
{
  "backend_port": 18080,
  "frontend_port": 15180
}
```

## PATCH /api/dev/worktrees/{worktree_id}/metadata

### 语义

- 更新 worktree metadata（目前仅允许 `description`/`plan_path`）。
- 若 worktree 不存在，返回 `ok=false` 且 `error=worktree_not_found`。

### 示例请求（curl）

```bash
curl --noproxy '*' -sS -X PATCH \
  "http://127.0.0.1:8000/api/dev/worktrees/8f05/metadata" \
  -H 'content-type: application/json' \
  -d '{
    "description": "Anchor + Zhongshu incremental draw/delta",
    "plan_path": "docs/plan/2026-02-06-anchor-zhongshu-draw-delta-incremental.md"
  }'
```

### 示例请求体（json）

```json
{
  "description": "Anchor + Zhongshu incremental draw/delta",
  "plan_path": "docs/plan/2026-02-06-anchor-zhongshu-draw-delta-incremental.md"
}
```

### 示例响应（json）

```json
{
  "ok": true,
  "metadata": {
    "description": "Anchor + Zhongshu incremental draw/delta",
    "plan_path": "docs/plan/2026-02-06-anchor-zhongshu-draw-delta-incremental.md",
    "created_at": "2026-02-06T19:10:00Z",
    "owner": "rick",
    "ports": {"backend_port": 18080, "frontend_port": 15180}
  }
}
```
