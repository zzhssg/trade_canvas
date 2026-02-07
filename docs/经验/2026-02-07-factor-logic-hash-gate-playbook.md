---
title: 经验：factor 代码变更触发数据失效与一键重建
status: 已完成
created: 2026-02-07
updated: 2026-02-07
---

# 经验：factor 代码变更触发数据失效与一键重建

## 场景与目标

当 factor 代码/关键参数变化后，旧的 factor 数据如果继续被读取，会出现“看起来有数据，实际上语义已过期”的隐性风险。
目标是把这个风险前置为显式 fail-safe，并提供可自动恢复的重建入口。

## 做对了什么（可复用动作）

- 在 `factor_series_state` 引入 `logic_hash`，把“代码+关键参数版本”写入状态表。
- 读路径统一加门禁：
  - 缺失 hash -> `409 stale_factor_logic_hash:missing`
  - 不匹配 -> `409 stale_factor_logic_hash:mismatch:*`
- 新增 `POST /api/factor/rebuild`：按 `series_id` 清空并重建 factor（可选 overlay）。
- 增加回归测试：先构造 stale hash，再调用 rebuild，验证读口恢复 200。

## 为什么有效

- 从“隐性过期”改为“显式拒绝”，避免策略/UI 消费过期产物。
- 通过重建 API 提供标准修复路径，减少手工清库和误操作。
- 测试闭环覆盖“失效 -> 修复 -> 恢复”的完整链路。

## 复用方式（下次怎么做）

1) 新增任何“可持久化产物”模块时，同步设计 `logic_hash` 字段。
2) 在读 API 统一调用 `ensure_*_logic_valid()`，先校验后返回。
3) 同步提供最小重建入口（按 series、幂等、可回滚）。
4) 验收固定执行：
- `pytest -q`
- `cd frontend && npm run build`
- `bash docs/scripts/doc_audit.sh`

## 关联

- 关键文件：
  - `backend/app/factor_store.py`
  - `backend/app/factor_orchestrator.py`
  - `backend/app/main.py`
  - `backend/tests/test_factor_slices_api.py`
  - `docs/core/api/v1/http_factor.md`
