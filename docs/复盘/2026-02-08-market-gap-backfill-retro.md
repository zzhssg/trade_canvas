---
title: 复盘：1m 图 gap 未自动补齐导致时间跳变
status: done
created: 2026-02-08
updated: 2026-02-08
---

# 复盘：1m 图 gap 未自动补齐导致时间跳变

## 背景

本轮问题来自市场主链路联调：
- 用户在 1m 图看到时间从 `02-28 15:15` 直接跳到 `02-08 20:13`（本地时区显示）。
- 预期是 gap 能被补齐，而不是直接拼接“旧尾 + 新头”。

涉及链路：
- `backend/app/main.py`（`/ws/market` subscribe/catchup）
- `frontend/src/widgets/ChartView.tsx`（收到 `gap` 后的补拉逻辑）
- `backend/app/ingest_binance_ws.py`（实时 ingest）

## 具体错误（可复现现象/证据）

现象：
- 订阅后能收到最新实时 candle，但历史缺口不会自动补齐。

证据：
- 后端此前只在发现缺口时发送 `gap`，不主动回源补齐（`backend/app/main.py`）。
- 前端收到 `gap` 后再次调用本地 `/api/market/candles`，本地没有的数据依然拿不到（`frontend/src/widgets/ChartView.tsx`）。

## 影响与代价

- 图表连续性被破坏，用户会误判数据链路不稳定。
- 后续排障成本高：看起来像“前端渲染问题”，实则是“缺历史回补策略”。
- 若类似问题出现在策略联调，可能导致对信号连续性的错误判断。

## 根因（1-3 条）

1. WS gap 协议只有“告警”（`gap`），没有“自动补齐”执行路径。  
2. 回补能力分散在 replay 侧，市场实时链路没有直接复用。  
3. 缺少“gap 回补开关”的默认治理策略（可灰度/可快速回滚）。

## 如何避免（检查清单）

开发前：
- [ ] 先确认“gap 发现后谁负责补齐”：服务端、客户端还是双保险。  
- [ ] 新增行为变更必须先定义 kill-switch（默认关闭）。  
- [ ] 先写 1 条“能失败”的回归测试（先红后绿）。

开发中：
- [ ] 避免重复实现 backfill，优先抽公共模块复用。  
- [ ] gap 处理必须同时覆盖 subscribe catchup 与后续 live 追平场景。  
- [ ] 补齐失败必须有可观测信号（日志/错误码/指标）。

验收时：
- [ ] `pytest -q` 必过，且包含 gap 回补测试。  
- [ ] `bash docs/scripts/doc_audit.sh` 必过。  
- [ ] 联调至少验证一次“缺口存在 -> 自动补齐 -> 图表连续”。

## 关联与验证

- 关键文件：
  - `backend/app/market_backfill.py`
  - `backend/app/main.py`
  - `backend/app/replay_package_service_v1.py`
  - `backend/tests/test_market_ws.py`
  - `docs/core/market-kline-sync.md`
- 验证命令：
  - `pytest -q`
  - `bash docs/scripts/doc_audit.sh`
