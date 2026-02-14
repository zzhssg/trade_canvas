---
name: tc-context-compact
description: Use when long sessions, context pressure, or task switching appears; enforce strategic compact with snapshot-before-switch and explicit resume contract.
metadata:
  short-description: 上下文治理（战略 compact + 快照恢复）
---

# tc-context-compact（上下文治理）

目标：把“上下文快满/任务切换/阶段切换”的风险变成可控流程，避免丢失关键决策与重复探索。

统一真源：
- 门禁与交付要求以 `AGENTS.md` 和 `docs/core/agent-workflow.md` 为准。
- 本 skill 只负责上下文治理，不替代 `tc-planning`、`tc-verify`、`tc-acceptance-e2e`。

---

## 1) 何时必须触发

- 长会话连续推进，出现“响应变慢、重复问答、上下文漂移”迹象。
- 任务从“探索/调试”切到“实现/验收”。
- 一个里程碑完成后，准备开启下一里程碑。
- 需要从当前会话切到新会话继续同一任务。

---

## 2) 何时不要 compact

- 正在同一实现链路中段（变量、文件、断言还在持续联动）。
- 关键结论还未落盘（plan / 经验卡 / 命令证据未写）。
- 还没给出“下一步唯一动作”。

---

## 3) compact 前快照（强制）

先写会话快照，再 compact 或切会话。建议路径：
- `output/context/YYYY-MM-DD-<topic>-snapshot.md`

推荐优先使用自动化脚本（避免漏字段）：

```bash
python3 scripts/context_snapshot.py save \
  --topic <topic> \
  --phase 执行方案 \
  --goal "<当前目标>" \
  --next-step "<下一步唯一动作>" \
  --acceptance "<验收命令>" \
  --rollback "<回滚方式>" \
  --files "backend/app/...,frontend/src/..." \
  --evidence "<命令+关键输出+产物路径>"
```

快照最小字段（缺一不可）：
- 当前目标（本轮要达成什么）
- 已验证结论（含命令与关键输出）
- 未解决问题与阻塞
- 下一步唯一动作（第一条命令）
- 关键文件路径列表（便于恢复）
- 回滚点（可撤销方式）

建议附带命令：

```bash
git status --short
git diff --stat
```

---

## 4) 执行模式

### A) 软 compact（同会话继续）

- 在当前回复末尾输出 6-10 行“阶段摘要”。
- 摘要结构固定：目标 / 已完成 / 未完成 / 风险 / 下一步。
- 若客户端支持 compact 功能，再执行 compact。

### B) 硬切换（新会话继续）

- 先落盘快照文件，再开新会话。
- 新会话第一条消息只带：快照路径 + 当前目标 + 下一步命令。
- 禁止在新会话重新做已验证过的探索。

新会话可先自动回显最近快照：

```bash
python3 scripts/context_snapshot.py resume --lines 80
```

---

## 5) 恢复契约（新会话第一屏）

恢复后第一屏必须回答：
- 从哪份快照恢复（路径）
- 当前阶段（分析/方案/执行）
- 本轮验收命令
- 若失败，回滚路径

---

## 6) 不通过判定

- 无快照直接切会话。
- 快照无“下一步唯一动作”。
- 切换后重复执行已明确失败的旧路径。
- compact 后无法说清本轮验收命令与回滚方式。

---

## 7) 与其它 skills 的衔接

推荐串联：
- `tc-planning`（先定计划）→ `tc-context-compact`（阶段切换治理）→ `tc-verify`（交付前门禁）→ `tc-learning-loop`（经验沉淀）
