---
title: Dev（Worktree / Ports）HTTP API v1
status: done
created: 2026-02-05
updated: 2026-02-11
---

# Dev（Worktree / Ports）HTTP API v1

本文件覆盖 `/api/dev/**`（开发者面板 / worktree 生命周期管理）相关 endpoints。

Base URL（本地默认）：
- `http://127.0.0.1:8000`

> 说明：本文件是 `docs/scripts/api_docs_audit.py` 的门禁输入之一；章节标题与示例格式必须遵循 `docs/core/api/v1/README.md` 的约定。

## GET /api/dev/worktrees

```bash
curl --noproxy '*' -fsS http://127.0.0.1:8000/api/dev/worktrees
```

```json
{
  "worktrees": [
    {
      "id": "a1b2c3d4",
      "path": "/Users/rick/code/trade_canvas",
      "branch": "main",
      "commit": "deadbeef",
      "is_detached": false,
      "is_main": true,
      "metadata": null,
      "services": {
        "backend": {
          "running": true,
          "port": 8000,
          "pid": 12345,
          "url": "http://127.0.0.1:8000"
        },
        "frontend": {
          "running": false,
          "port": 5173,
          "pid": null,
          "url": null
        }
      }
    }
  ]
}
```

### 语义

- 返回 worktree 列表（来自 `git worktree list --porcelain` + `.worktree-meta/*.json`）。
- `services.*.running` 通过 PID 存活判断；如果 PID 不存在或已退出，会返回 `running=false`。

## GET /api/dev/worktrees/{worktree_id}

```bash
curl --noproxy '*' -fsS http://127.0.0.1:8000/api/dev/worktrees/a1b2c3d4
```

```json
{
  "id": "a1b2c3d4",
  "path": "/Users/rick/worktree-feature-my-feature",
  "branch": "feature/my-feature",
  "commit": "cafebabe",
  "is_detached": false,
  "is_main": false,
  "metadata": {
    "description": "实现 XXX 功能，包括 A、B、C 三个模块",
    "plan_path": "docs/plan/2026-02-05-my-feature.md",
    "created_at": "2026-02-05T02:00:00+00:00",
    "owner": "rick",
    "ports": {
      "backend": 8001,
      "frontend": 5174
    }
  },
  "services": {
    "backend": {
      "running": false,
      "port": 8001,
      "pid": null,
      "url": null
    },
    "frontend": {
      "running": false,
      "port": 5174,
      "pid": null,
      "url": null
    }
  }
}
```

### 语义

- 查询单个 worktree（`worktree_id` 为 worktree path 的 sha256 前 8 位）。
- 不存在时返回 404（`detail=worktree_not_found`）。

## GET /api/dev/ports/allocate

```bash
curl --noproxy '*' -fsS http://127.0.0.1:8000/api/dev/ports/allocate
```

```json
{
  "backend_port": 8001,
  "frontend_port": 5174
}
```

### 语义

- 返回“下一对可用端口”（默认后端从 8001 起、前端从 5174 起递增）。
- 仅做分配建议，不会自动写入 `.worktree-meta/index.json`；真正分配在创建/启动 worktree 时发生。

## POST /api/dev/worktrees

```bash
curl --noproxy '*' -fsS -X POST http://127.0.0.1:8000/api/dev/worktrees   -H "Content-Type: application/json"   -d @- <<'JSON'
{
  "branch": "feature/my-feature",
  "description": "实现 XXX 功能，包括 A、B、C 三个模块",
  "plan_path": "docs/plan/2026-02-05-my-feature.md",
  "base_branch": "main"
}
JSON
```

```json
{
  "branch": "feature/my-feature",
  "description": "实现 XXX 功能，包括 A、B、C 三个模块",
  "plan_path": "docs/plan/2026-02-05-my-feature.md",
  "base_branch": "main"
}
```

```json
{
  "ok": true,
  "worktree": {
    "id": "a1b2c3d4",
    "path": "/Users/rick/worktree-feature-my-feature",
    "branch": "feature/my-feature",
    "commit": "",
    "is_detached": false,
    "is_main": false,
    "metadata": {
      "description": "实现 XXX 功能，包括 A、B、C 三个模块",
      "plan_path": "docs/plan/2026-02-05-my-feature.md",
      "created_at": "2026-02-05T02:00:00+00:00",
      "owner": "rick",
      "ports": {
        "backend": 8001,
        "frontend": 5174
      }
    },
    "services": null
  },
  "error": null
}
```

### 语义

- 创建一个新的 git worktree，并写入元数据 `.worktree-meta/{id}.json`。
- `description` 最少 20 字符（不满足会返回 `ok=false`）。
- 若分支不存在，会从 `base_branch` 创建分支后再创建 worktree。

## PATCH /api/dev/worktrees/{worktree_id}/metadata

```bash
curl --noproxy '*' -fsS -X PATCH http://127.0.0.1:8000/api/dev/worktrees/a1b2c3d4/metadata   -H "Content-Type: application/json"   -d @- <<'JSON'
{
  "description": "实现 XXX 功能（补充：含验收与回滚口径）",
  "plan_path": "docs/plan/2026-02-05-my-feature.md"
}
JSON
```

```json
{
  "description": "实现 XXX 功能（补充：含验收与回滚口径）",
  "plan_path": "docs/plan/2026-02-05-my-feature.md"
}
```

```json
{
  "ok": true,
  "metadata": {
    "description": "实现 XXX 功能（补充：含验收与回滚口径）",
    "plan_path": "docs/plan/2026-02-05-my-feature.md",
    "created_at": "2026-02-05T02:00:00+00:00",
    "owner": "rick",
    "ports": {
      "backend": 8001,
      "frontend": 5174
    }
  },
  "error": null
}
```

### 语义

- 仅更新 `.worktree-meta/{id}.json`；不做 git 操作。
- worktree 不存在时返回：`ok=false, error=worktree_not_found`。

## POST /api/dev/worktrees/{worktree_id}/start

```bash
curl --noproxy '*' -fsS -X POST http://127.0.0.1:8000/api/dev/worktrees/a1b2c3d4/start   -H "Content-Type: application/json"   -d @- <<'JSON'
{
  "backend_port": 8001,
  "frontend_port": 5174
}
JSON
```

```json
{
  "backend_port": 8001,
  "frontend_port": 5174
}
```

```json
{
  "ok": true,
  "services": {
    "backend": {
      "running": true,
      "port": 8001,
      "pid": 22222,
      "url": "http://127.0.0.1:8001"
    },
    "frontend": {
      "running": true,
      "port": 5174,
      "pid": 33333,
      "url": "http://127.0.0.1:5174"
    }
  },
  "error": null
}
```

### 语义

- 启动该 worktree 的后端与前端服务，并把 PID 写入 `.worktree-meta/index.json` 的 `active_services`。
- 若端口未指定，会尝试从 metadata 中读取或自动分配。
- 该操作有副作用（启动进程、占用端口）。

## POST /api/dev/worktrees/{worktree_id}/stop

```bash
curl --noproxy '*' -fsS -X POST http://127.0.0.1:8000/api/dev/worktrees/a1b2c3d4/stop
```

```json
{
  "ok": true,
  "error": null
}
```

### 语义

- 停止该 worktree 的服务（向对应进程组发送 SIGTERM），并从 `active_services` 中清理记录。
- 若该 worktree 当前没有活跃服务，可能返回 `ok=false`（以实现为准）。

## DELETE /api/dev/worktrees/{worktree_id}

```bash
curl --noproxy '*' -fsS -X DELETE http://127.0.0.1:8000/api/dev/worktrees/a1b2c3d4   -H "Content-Type: application/json"   -d @- <<'JSON'
{
  "force": false
}
JSON
```

```json
{
  "force": false
}
```

```json
{
  "ok": true,
  "error": null
}
```

### 语义

- 停止服务后删除 worktree，并将 `.worktree-meta/{id}.json` 归档到 `.worktree-meta/archive/`。
- `force=true` 时会以 `git worktree remove --force` 删除（谨慎使用）。
