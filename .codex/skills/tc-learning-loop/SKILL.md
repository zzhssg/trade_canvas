---
name: tc-learning-loop
description: Use after delivery/debug milestones to extract atomic lessons with evidence and confidence, then promote stable patterns into reusable project skills.
metadata:
  short-description: 交付后学习闭环（原子经验卡）
---

# tc-learning-loop（学习闭环）

目标：把“本轮踩坑与解法”沉淀为可复用资产，减少重复犯错和重复提示词成本。

统一真源：
- 交付门禁、Doc Impact 与回滚要求以 `AGENTS.md` DoD 为准。
- 本 skill 负责“经验抽取与沉淀”，不替代 `tc-verify` / `tc-acceptance-e2e`。

---

## 1) 何时触发

- 任意 `feat` / `fix` / `refactor` 完成并准备交付时。
- 关键 bug 完成根因定位并修复后。
- 一次 E2E/门禁失败后找到可复用修复模式时。

---

## 2) 输入与输出

输入（至少 3 项）：
- 关键 diff（改了哪些路径）
- 至少一条门禁命令输出（`pytest -q` / `npm run build` / `quality_gate` / `e2e_acceptance`）
- 一条可复核证据（日志、trace、截图、产物路径）

输出（必须）：
- 在 `docs/经验/` 追加或新建经验文档，写入“原子经验卡”。
- 卡片必须含：触发条件、动作、证据、置信度、适用/不适用边界。

---

## 3) 原子经验卡模板（强制字段）

```markdown
### [LL-YYYY-MM-DD-序号] <一句话标题>
- Trigger（何时触发）：
- Action（采取动作）：
- Evidence（命令 + 关键输出 + 产物路径）：
- Confidence（0.3-0.9）：
- Scope（适用范围）：
- Anti-Scope（不适用范围）：
- Next-Check（下次如何复核）：
```

规则：
- 每轮最多沉淀 1-3 张卡；禁止“流水账式大段复盘”。
- 无证据不允许写高置信度（`>=0.8`）。
- 若同类卡片连续 2 次失败，必须降置信度并补反例。

---

## 4) 置信度与升级规则

- 初次沉淀：`0.5-0.7`
- 第二次独立任务复用成功：`+0.1`
- 第三次复用成功且无反例：可升到 `>=0.8`
- 出现反例或失效：`-0.2` 并补 Anti-Scope

晋级条件（经验 → skill）：
- 同一经验卡 `confidence >= 0.8` 且至少 3 次独立复用成功。
- 满足后进入 `tc-skill-authoring`，把经验升级为项目 skill 规则。

---

## 5) 与 docs / 门禁联动

- 经验文档更新后，若本轮变更包含 docs，需跑：

```bash
bash docs/scripts/doc_audit.sh
```

- 交付汇报中建议增加一行：
  - `Learning Loop: +N cards (path: docs/经验/...)`

---

## 6) 不通过判定

- 经验卡缺少证据或无法复核。
- 经验卡只有“结果”，没有“触发条件/适用边界”。
- 把一次性偶发问题当成通用规律强推。
- 明明沉淀了经验，却没有反馈到 plan/skill 的后续动作。
