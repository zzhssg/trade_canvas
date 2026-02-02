# Frontend 运行手册

本前端用于图表与操作台（Vite + React + TS + Tailwind + Router + Zustand + React Query + lightweight-charts）。

## 启动

```bash
cd frontend
npm install
npm run dev
```

打开 Vite 打印的 URL（默认 `http://localhost:5173`）。

## Troubleshooting

### Error: Port 5173 is already in use

本项目在 `frontend/vite.config.ts` 里设置了 `server.strictPort: true`（保证端口固定，便于 E2E/书签/脚本），所以当 5173 被占用时会直接报错。

- 直接释放端口并重启：

```bash
cd frontend
npm run dev:restart
```

- 或者手动找出占用进程并结束（macOS / Linux）：

```bash
lsof -nP -iTCP:5173 -sTCP:LISTEN
kill <PID>
```

- 临时换端口（注意：E2E 默认还是指向 5173，可用 `E2E_BASE_URL` 覆盖）：

```bash
cd frontend
npm run dev:port -- 5174
```

## 连接后端 API（开发态）

Vite dev server 与后端（默认 `http://localhost:8000`）是跨端口的，建议设置：

```bash
cd frontend
export VITE_API_BASE_URL="http://127.0.0.1:8000"
npm run dev
```

兼容：也可使用 `VITE_API_BASE`（低优先级，建议迁移到 `VITE_API_BASE_URL`）。

## 前后端联调 E2E（验收）

在仓库根目录一键跑通：

```bash
bash scripts/e2e_acceptance.sh
```

## 备注

默认后端地址：`http://localhost:8000`（WS：`ws://localhost:8000`）。
