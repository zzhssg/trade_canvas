---
title: "市场 gap 回补（公共能力 + kill-switch + 回归测试）"
status: done
created: 2026-02-08
updated: 2026-02-09
---

# 市场 gap 回补（公共能力 + kill-switch + 回归测试）

## 问题背景

市场主链路联调中，用户在 1m 图看到时间从 `02-28 15:15` 直接跳到 `02-08 20:13`（本地时区显示），预期 gap 能被补齐而不是直接拼接"旧尾 + 新头"。

具体错误：后端此前只在发现缺口时发送 `gap`，不主动回源补齐；前端收到 `gap` 后再次调用本地 `/api/market/candles`，本地没有的数据依然拿不到。图表连续性被破坏，看起来像"前端渲染问题"，实则是"缺历史回补策略"。

## 根因

1. WS gap 协议只有"告警"（`gap`），没有"自动补齐"执行路径。
2. 回补能力分散在 replay 侧，市场实时链路没有直接复用。
3. 缺少"gap 回补开关"的默认治理策略（可灰度/可快速回滚）。

## 解法

- **抽出公共回补模块**：`backend/app/market_backfill.py`，让 replay 与 market realtime 复用同一套 CCXT 回补能力。
- **引入后端开关**：`TRADE_CANVAS_ENABLE_MARKET_GAP_BACKFILL`（默认 `0`），实现灰度放量与快速回滚。
- **先补测试再收口**：新增 `test_ws_subscribe_gap_backfill_enabled_rehydrates_missing_candles` 保证行为可回归。
- **同步文档**：更新 `docs/core/market-kline-sync.md` 与 `docs/core/api/v1/ws_market.md`，保证契约与实现一致。

## 为什么有效

- 公共能力减少重复代码，避免 replay/market 各自演化后口径漂移。
- kill-switch 让高风险行为具备"秒级降级"能力，避免上线后只能改代码回滚。
- 回归测试把"补齐成功才不发 gap"的预期固定为机器可验证规则。

## 检查清单

**开发前**
- [ ] 先确认"gap 发现后谁负责补齐"：服务端、客户端还是双保险。
- [ ] 新增行为变更必须先定义 kill-switch（默认关闭）。
- [ ] 先写 1 条"能失败"的回归测试（先红后绿）。

**开发中**
- [ ] 避免重复实现 backfill，优先抽公共模块复用。
- [ ] gap 处理必须同时覆盖 subscribe catchup 与后续 live 追平场景。
- [ ] 补齐失败必须有可观测信号（日志/错误码/指标）。
- [ ] 任何"主链路新增自动行为"默认都加 `TRADE_CANVAS_ENABLE_*` 开关（默认关闭）。

**验收时**
- [ ] `pytest -q` 必过，且包含 gap 回补测试。
- [ ] `bash docs/scripts/doc_audit.sh` 必过。
- [ ] 联调至少验证一次"缺口存在 -> 自动补齐 -> 图表连续"。

## 关联

- `backend/app/market_backfill.py`
- `backend/app/main.py`
- `backend/app/replay_package_service_v1.py`
- `backend/tests/test_market_ws.py`
- `docs/core/market-kline-sync.md`
- `docs/core/api/v1/ws_market.md`
