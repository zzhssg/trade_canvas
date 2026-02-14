---
name: tc-verify
description: Use when implementing refactors or behavior changes to enforce clean-architecture gates (no compatibility layers, no legacy leftovers, bounded complexity, and reproducible evidence) before delivery.
metadata:
  short-description: 统一质量门禁（禁兼容/禁遗留/禁堆债）
---

# tc-verify（统一质量门禁）

目标：把“代码干净整洁”从口头要求变成强制门禁，默认拒绝“兼容层 + 遗留双轨 + 临时 hack 永久化”。

## 何时必须触发

- 任何 `feat` / `fix` / `refactor` 行为改动（无论是否跨模块）。
- 任何“重构旧链路”的任务（尤其是你决定不做向后兼容时）。
- 宣称“可交付/可验收/完成”之前。

## 一句话规则（硬约束）

- **不兼容旧实现，不保留遗留代码，不引入过渡双轨。**
- 同一轮改动里，必须做到“新路径可验收 + 旧路径可删除 + 证据可复核”。

## 执行顺序（必须按顺序）

1) 先跑自动门禁脚本（机器判定）  
2) 再过结构化人工复核（设计判定）  
3) 最后附交付证据（可复核判定）

---

## 1) 自动门禁（机器判定）

推荐命令：

```bash
bash scripts/quality_gate.sh
```

若本轮包含新增 factor，先确认脚手架文件齐全且无手写遗漏：

```bash
python3 scripts/new_factor_scaffold.py --factor <name> --depends-on <dep1,dep2> --dry-run
```

常用变体：

```bash
# 对比 main 分支改动（含本分支提交 + 工作区改动）
bash scripts/quality_gate.sh --base main

# 要求“旧路径必须已删除”（删除清单逐行写相对路径）
bash scripts/quality_gate.sh --delete-list docs/plan/delete-list.txt

# 仅跑结构门禁，不跑 pytest / 前端 build（本地快速迭代）
bash scripts/quality_gate.sh --fast
```

`quality_gate.sh` 默认检查：
- 文件体量门禁（Python/TS/TSX/hook 行数约束）
- Python 结构门禁（函数参数 ≤8、dataclass 字段 ≤15）
- 兼容/遗留关键词门禁（新增兼容层直接 fail）
- 临时债标记门禁（`TODO/FIXME/HACK` 默认 fail）
- 按触达面自动执行 `pytest -q` 与 `cd frontend && npm run build`

---

## 2) 人工复核（设计判定，必须给结论）

每次至少回答以下问题并写进交付说明：

1. **Delete Check**：本次删掉了哪些旧文件/旧函数/旧接口？  
2. **No Dual Path**：是否仍存在“新旧双轨同时可走”？（若是，判定不通过）  
3. **Boundary Check**：是否破坏单向依赖 `ingest -> store -> factor -> overlay -> read_model -> route`？  
4. **Contract Check**：`candle_id` 是否仍保持确定性对齐（`{symbol}:{timeframe}:{open_time}` 或等价稳定标识）？  
5. **Rollback Check**：最短回滚路径是什么（`git revert <sha>` 或开关）？

---

## 3) P/R 快检（必须落盘）

交付说明至少明确：

- 本次采用的 `P*`：至少 2 个（建议 `P2`/`P10`/`P14`）
- 本次排除或修复的 `R*`：至少 2 个（建议 `R2`/`R5`/`R6`/`R7`）

若命中 `R6`（重复实现）或 `R7`（通用/专用混杂），默认不允许“先交付后重构”。

---

## 4) 与其它 skills 的衔接

推荐编排（最小覆盖）：

- `tc-planning`：产出计划与 A/B 方案
- `tc-e2e-gate`：确保主链路 E2E 用户故事可运行
- `tc-verify`：在交付前执行统一质量门禁
- `tc-acceptance-e2e`：最终验收与证据归档

调试场景：

- `tc-debug` 修复后，必须补跑一次 `tc-verify`，防止“修复 bug 同时引入新债”。

---

## 5) 不通过判定（任一命中即失败）

- 发现新增兼容层/遗留分支，但没有同步删除旧实现。
- 自动门禁命令失败仍宣称“完成”。
- 只有功能通过，没有结构与回滚证据。
- 交付说明未给 `Doc Impact`、`P/R`、`交付三问`。

---

## 6) 交付最小模板（可直接复用）

```text
Gate:
- Command: bash scripts/quality_gate.sh --base main
- Output: <关键输出摘要>
- Artifacts: <如 output/...>

Delete Check:
- Removed: <旧文件/旧函数/旧接口>
- Dual Path: no

Design Check:
- P*: P2, P10
- R*: R6(removed), R7(not found)

Doc Impact: yes/no
Rollback: git revert <sha>
```
