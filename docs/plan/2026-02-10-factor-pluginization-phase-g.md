---
title: Factor 完全插件化（Phase G：前端因子目录动态化）
status: done
owner: codex
created: 2026-02-10
updated: 2026-02-10
---

## 目标

- 消除前端因子面板对静态目录常量的依赖，改为从后端动态拉取。
- 让因子开关目录与后端 `factor_manifest` 拓扑顺序保持同源，减少新增因子时的双端同步成本。
- 保留 fallback 机制：后端目录接口不可用时，前端仍可用默认目录正常渲染。

## 变更范围

- 后端目录接口：
  - `/Users/rick/code/trade_canvas/backend/app/schemas.py`
    - 新增 `FactorCatalogSubFeatureV1` / `FactorCatalogItemV1` / `GetFactorCatalogResponseV1`。
  - `/Users/rick/code/trade_canvas/backend/app/factor_catalog.py`
    - 新增目录构建器：从 manifest 读取标准因子 + 追加 `sma/signal` 虚拟分组。
  - `/Users/rick/code/trade_canvas/backend/app/factor_routes.py`
    - 新增 `GET /api/factor/catalog`。
  - `/Users/rick/code/trade_canvas/backend/tests/test_factor_catalog_api.py`
    - 覆盖目录接口结构、默认顺序和默认可见性。
- 前端目录消费：
  - `/Users/rick/code/trade_canvas/frontend/src/services/factorCatalog.ts`
    - 新增动态拉取 + 本地缓存 + fallback 目录。
  - `/Users/rick/code/trade_canvas/frontend/src/parts/FactorPanel.tsx`
    - 改为使用 `useFactorCatalog()` 动态目录。
  - `/Users/rick/code/trade_canvas/frontend/src/widgets/ChartView.tsx`
    - 子特性父级映射改为基于动态目录计算。
- 文档同步：
  - `/Users/rick/code/trade_canvas/docs/core/api/v1/http_factor.md`
  - `/Users/rick/code/trade_canvas/docs/core/architecture.md`
  - `/Users/rick/code/trade_canvas/docs/core/factor-modular-architecture.md`

## 验收

- `pytest -q backend/tests/test_factor_catalog_api.py`
- `pytest -q`
- `cd frontend && npm run build`
- `bash docs/scripts/doc_audit.sh`

## 回滚

- 单提交回滚：`git revert <sha>`。
- 最小文件回退：
  - `/Users/rick/code/trade_canvas/backend/app/factor_catalog.py`
  - `/Users/rick/code/trade_canvas/backend/app/factor_routes.py`
  - `/Users/rick/code/trade_canvas/frontend/src/services/factorCatalog.ts`
  - `/Users/rick/code/trade_canvas/frontend/src/parts/FactorPanel.tsx`
  - `/Users/rick/code/trade_canvas/frontend/src/widgets/ChartView.tsx`
