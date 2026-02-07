---
title: API v1 · Dev（HTTP）
status: draft
created: 2026-02-07
updated: 2026-02-07
---

# API v1 · Dev（HTTP）

## GET /api/dev/worktrees

### 示例（curl）

```bash
curl --noproxy '*' -sS "http://127.0.0.1:8000/api/dev/worktrees"
```

### 示例响应（json）

```json
{
  "worktrees": [
    {
      "id": "ade8",
      "path": "/Users/rick/.codex/worktrees/ade8/trade_canvas",
      "branch": "codex/replay-ui",
      "commit": "abc123",
      "is_detached": false,
      "is_main": false,
      "metadata": {
        "description": "replay ui",
        "plan_path": "docs/plan/2026-02-07-replay-ui.md",
        "created_at": "2026-02-07",
        "owner": "rick",
        "ports": {"backend": 18080, "frontend": 15180}
      },
      "services": null
    }
  ]
}
```

### 语义

- 列出全部 worktree 及其元数据/服务状态，用于 dev panel 展示与运维。

## GET /api/dev/worktrees/{worktree_id}

### 示例（curl）

```bash
curl --noproxy '*' -sS "http://127.0.0.1:8000/api/dev/worktrees/ade8"
```

### 示例响应（json）

```json
{
  "id": "ade8",
  "path": "/Users/rick/.codex/worktrees/ade8/trade_canvas",
  "branch": "codex/replay-ui",
  "commit": "abc123",
  "is_detached": false,
  "is_main": false,
  "metadata": {
    "description": "replay ui",
    "plan_path": "docs/plan/2026-02-07-replay-ui.md",
    "created_at": "2026-02-07",
    "owner": "rick",
    "ports": {"backend": 18080, "frontend": 15180}
  },
  "services": null
}
```

### 语义

- 查询单个 worktree 的详情（用于面板展开或脚本自检）。

## POST /api/dev/worktrees

### 示例（curl）

```bash
curl --noproxy '*' -sS -X POST \
  "http://127.0.0.1:8000/api/dev/worktrees" \
  -H "Content-Type: application/json" \
  -d '{"branch":"codex/replay-ui","description":"replay ui iteration","plan_path":"docs/plan/2026-02-07-replay-ui.md","base_branch":"main"}'
```

### 示例请求（json）

```json
{
  "branch": "codex/replay-ui",
  "description": "replay ui iteration",
  "plan_path": "docs/plan/2026-02-07-replay-ui.md",
  "base_branch": "main"
}
```

### 示例响应（json）

```json
{
  "ok": true,
  "worktree": {
    "id": "ade8",
    "path": "/Users/rick/.codex/worktrees/ade8/trade_canvas",
    "branch": "codex/replay-ui",
    "commit": "abc123",
    "is_detached": false,
    "is_main": false,
    "metadata": {
      "description": "replay ui iteration",
      "plan_path": "docs/plan/2026-02-07-replay-ui.md",
      "created_at": "2026-02-07",
      "owner": "rick",
      "ports": {"backend": 18080, "frontend": 15180}
    },
    "services": null
  },
  "error": null
}
```

### 语义

- 创建新的 worktree，并写入描述/计划路径等元数据。

## POST /api/dev/worktrees/{worktree_id}/start

### 示例（curl）

```bash
curl --noproxy '*' -sS -X POST \
  "http://127.0.0.1:8000/api/dev/worktrees/ade8/start" \
  -H "Content-Type: application/json" \
  -d '{"backend_port":18080,"frontend_port":15180}'
```

### 示例请求（json）

```json
{"backend_port":18080,"frontend_port":15180}
```

### 示例响应（json）

```json
{
  "ok": true,
  "services": {
    "backend": {"running": true, "port": 18080, "pid": 12345, "url": "http://127.0.0.1:18080"},
    "frontend": {"running": true, "port": 15180, "pid": 23456, "url": "http://127.0.0.1:15180"}
  },
  "error": null
}
```

### 语义

- 启动指定 worktree 的前后端服务（可指定端口）。

## POST /api/dev/worktrees/{worktree_id}/stop

### 示例（curl）

```bash
curl --noproxy '*' -sS -X POST \
  "http://127.0.0.1:8000/api/dev/worktrees/ade8/stop"
```

### 示例响应（json）

```json
{"ok": true, "error": null}
```

### 语义

- 停止指定 worktree 的前后端服务。

## DELETE /api/dev/worktrees/{worktree_id}

### 示例（curl）

```bash
curl --noproxy '*' -sS -X DELETE \
  "http://127.0.0.1:8000/api/dev/worktrees/ade8" \
  -H "Content-Type: application/json" \
  -d '{"force":false}'
```

### 示例请求（json）

```json
{"force": false}
```

### 示例响应（json）

```json
{"ok": true, "error": null}
```

### 语义

- 删除指定 worktree（可选 force）。

## GET /api/dev/ports/allocate

### 示例（curl）

```bash
curl --noproxy '*' -sS "http://127.0.0.1:8000/api/dev/ports/allocate"
```

### 示例响应（json）

```json
{"backend_port": 18080, "frontend_port": 15180}
```

### 语义

- 获取下一组可用端口（backend/frontend）。

## PATCH /api/dev/worktrees/{worktree_id}/metadata

### 示例（curl）

```bash
curl --noproxy '*' -sS -X PATCH \
  "http://127.0.0.1:8000/api/dev/worktrees/ade8/metadata" \
  -H "Content-Type: application/json" \
  -d '{"description":"replay ui","plan_path":"docs/plan/2026-02-07-replay-ui.md"}'
```

### 示例请求（json）

```json
{"description":"replay ui","plan_path":"docs/plan/2026-02-07-replay-ui.md"}
```

### 示例响应（json）

```json
{
  "ok": true,
  "metadata": {
    "description": "replay ui",
    "plan_path": "docs/plan/2026-02-07-replay-ui.md",
    "created_at": "2026-02-07",
    "owner": "rick",
    "ports": {"backend": 18080, "frontend": 15180}
  },
  "error": null
}
```

### 语义

- 更新 worktree 的描述/plan_path 元数据。
