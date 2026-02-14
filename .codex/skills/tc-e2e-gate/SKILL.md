---
name: tc-e2e-gate
description: "Enforce an E2E user-story gate for trade_canvas work: during planning require a complete end-to-end user story covering the main flow; during development require passing that E2E story before declaring done; during delivery require reporting the story, flow, produced data, and concrete evidence (commands + outputs/artifacts). Use when planning/implementing any feature or fix that spans multiple components or changes behavior."
---

# tc-e2e-gate（E2E 用户故事门禁）

目标：把“需求→实现→验收”收敛到一个 **可运行的 E2E 用户故事**，并把它作为完成门禁。

本技能分两阶段强约束：
- **需求规划阶段**：必须先写出“完整 E2E 用户故事”（覆盖本次需求主流程）。
- **需求开发阶段**：只有当该 E2E 用户故事验证通过，才能结束；交付汇报必须给出故事/流程/数据/证据。

配套资源：
- E2E 用户故事模板：`assets/e2e_user_story_template.md`
- 交付汇报模板：`assets/delivery_report_template.md`
- 示例（trade_canvas SMA cross）：`references/example_sma_cross_story.md`

---

## 1) 需求规划阶段（必须先落盘）

### 1.1 产出物（必须）

- 新建或更新 `docs/plan/YYYY-MM-DD-<topic>.md`（大改动必须；小改动也建议用同结构）。
- 在 plan 中写入一个 **完整 E2E 用户故事**（用 `assets/e2e_user_story_template.md` 作为骨架）。

补充约束（与验收门禁对齐）：
- **中/高风险变更必须有 plan**：任何非低风险改动（不止 docs/test/style）都必须落盘 `docs/plan/...`，并在 worktree metadata 里填写 `plan_path`（否则 `scripts/worktree_acceptance.sh` 会在验收门禁失败）。

### 1.2 E2E 用户故事的“完整”标准（硬约束）

- **单一主角 + 单一目标**：谁（persona）要完成什么（goal）。
- **明确入口与出口**：从哪个输入开始，到哪个可观测结果结束（返回值/接口响应/UI 状态/落盘数据）。
- **覆盖主流程**：至少跨越一次“输入→处理→存储→对外消费”的链路（按本需求的真实主链路）。
- **每一步都有断言**：每个步骤写清楚“怎么验证成功/失败”（可执行命令或可观测信号）。
- **必须有具体数值场景**：至少写出 1 个可复现的“具体数据点”（例如 candle_time/price/数量），禁止只写“预期成功/预期正确”。
- **写清产生的数据**：有哪些表/文件/消息/缓存 key/字段会被写入或改变（至少列出 key 字段）。
- **写清证据采集方式**：跑哪些命令，产出哪些输出/文件作为证据（至少一条可自动化命令）。

若本次是“新增 factor”：
- 规划阶段必须先记录脚手架命令与依赖关系（先 dry-run）：

```bash
python3 scripts/new_factor_scaffold.py --factor <name> --depends-on <dep1,dep2> --dry-run
```

- E2E 故事里要明确覆盖三段链路：`factor ingest event -> factor slice/head -> overlay draw`。

### 1.4 API 变更的前置检查（新增强约束）

当本次需求涉及“新增/修改 HTTP/WS/SSE endpoint”时，规划阶段必须额外完成：

- 先看存量 API（避免重复造接口/命名漂移）：
  - `bash docs/scripts/api_docs_audit.sh --list`
- 在 plan（`docs/plan/...`）中写清：
  - 你要新增/变更的 endpoint 列表（METHOD + PATH）
  - 对应要更新的文档文件：`docs/core/api/v1/...`
  - 至少 1 个“可执行示例”的具体数值（curl/json 示例里必须出现真实的 series_id/时间戳等）

### 1.3 规划阶段的退出条件（Definition of Ready）

- plan 已落盘，且 E2E 用户故事满足 1.2 的“完整”标准。
- E2E 的验证命令已写清（即便暂时会失败，也必须“能跑起来并失败在正确位置”）。

---

## 2) 需求开发阶段（必须跑通 E2E 才能结束）

### 2.1 开发过程的强约束

- 始终以 E2E 用户故事为主线拆解任务：任何子任务都必须能映射回 E2E 的某一步/某个断言。
- 优先“最小闭环”：先让 E2E 跑通再扩展能力；避免先堆接口/抽象导致验收缺位。
- 如果发现 E2E 用户故事不再覆盖主流程：先更新 plan（故事与断言），再继续实现。

### 2.2 开发阶段的退出条件（Definition of Done）

交付前必须完成：
- 统一质量门禁通过：`bash scripts/quality_gate.sh`（失败=未完成，先清理兼容层/遗留双轨/临时债）。
- E2E 用户故事对应的验证命令全部通过（退出码为 0）。
- **文档状态同步**：把本次相关文档的 `status/updated` 更新到正确阶段，并通过文档审计（参考 `docs/core/doc-status.md`）：
  - `docs/plan/YYYY-MM-DD-<topic>.md`：开发完成时应先更新为 `pending_acceptance/待验收`，并更新 `updated: YYYY-MM-DD`
  - 验收合并阶段再由 `scripts/worktree_acceptance.sh --auto-doc-status` 推进到 `online/已上线`
  - 任何受影响的核心文档/契约（`docs/core/` / `docs/core/contracts/`）：更新 `status` 与 `updated`
  - 运行 `bash docs/scripts/doc_audit.sh`（失败=未完成，先修）
- **API 文档完整性（新增强约束）**：
  - 在新增/修改任意 endpoint 之前，先跑一次清单查看（避免重复造接口/命名漂移）：
    - `bash docs/scripts/api_docs_audit.sh --list`
  - 新增/修改任意 HTTP/WS/SSE endpoint 时，必须同步更新 `docs/core/api/v1/`（同一轮改动内完成）：
    - 小节标题必须是 `## <METHOD> <PATH>` / `## WS <PATH>`
    - 必须包含可执行示例（`curl`/`wscat` 等）+ request/response 示例 json + `### 语义` 注释说明
  - 开发结束必须通过：`bash docs/scripts/doc_audit.sh`（其中包含 API docs audit；失败=未完成）
- 若有风险点无法覆盖：必须在 plan 的“未覆盖/风险”中明确写出，并给出后续补测计划。

---

## 3) 交付汇报阶段（必须给“故事+流程+数据+证据”）

在最终汇报中按 `assets/delivery_report_template.md` 输出，至少包含：
- **本次覆盖的主链路 E2E 用例**：明确 test file path + test name（让别人能“点开看 + 复现跑”）。
- **用户故事是什么**：persona/goal/入口/出口（简述）。
- **流程是什么**：按步骤列出（与 plan 中 E2E 步骤一一对应）。
- **产生了哪些数据**：列出关键表/文件/事件与关键字段（能定位/能查询）。
- **有哪些证据**：贴出验证命令 + 可观测结果（退出码/关键输出/关键文件路径）。
- **必须给“具体数值结果”**：把关键可观测值写出来（例如最后一根 K 的 close、WS 收到的 candle_time、DB 行数），并说明来源（UI/接口/SQL/trace）。
- **文档状态证据**：在汇报中补一条“已更新哪些文档的 status/updated + doc_audit 输出摘要”（确保别人能复核）。

## 4) 开发完成后复盘（强制 Code Review / 架构复核）

目的：把“做完功能”变成“做对方案 + 可维护”，尽量在交付前发现架构偏差与技术债，而不是后面用数倍时间返工。

### 4.1 触发时机（硬约束）

- 在 **2.2 的 DoD 全部满足之后**、**宣称完成/进入交付汇报之前** 必须做一次复盘式 code review。

### 4.2 输入材料（必须提供）

- `git diff --name-only`（本次改了哪些文件）
- `git diff` 或 `git show --stat`（改动规模与关键点）
- 本次 `docs/plan/...` 的 E2E 用户故事（要对照“每一步断言”）

### 4.3 Review Checklist（按顺序过一遍）

- **契约与不变量**：是否破坏/漂移了核心契约（HTTP/WS/schema/命名/主键/时序）；是否出现“口径不一致但测试没覆盖”的风险。
- **职责边界**：模块职责是否清晰；是否把临时逻辑塞进了不该放的层；是否产生了隐式耦合/全局状态依赖。
- **方案复核**：是否存在更简单/更一致的方案；当前实现是否只是“局部最优”（短期快、长期拖慢）。
- **两次设计证据**：是否在 plan 中给出过 A/B 方案并记录取舍；若没有，必须补齐再交付。
- **新增文件合理性**：每个新增文件是否说明“替代旧文件”或“现有文件无法扩展”的原因。
- **复杂度预算**：新增模块是否接近 `<=200` 行、抽象嵌套是否接近 `<=2` 层；超限是否给出收益说明和后续拆解计划。
- **可回滚性**：是否具备最短回滚路径（开关/feature flag/可 revert）；是否引入不可逆的数据写入或迁移风险。
- **测试与验收**：是否新增了“能失败的”回归保护；E2E 覆盖是否真实主链路；是否有关键边界条件未覆盖。
- **可观测性**：关键路径是否有足够的日志/错误信息/trace 证据点，能支撑排障与回归定位。
- **注释质量**：注释是否描述了非显然信息（设计意图/权衡/边界），而不是复述代码字面行为。
- **技术债清单**：是否引入了临时 hack、重复造轮子、TODO/注释债、数据兼容债；债务是否被显式记录与分级。

### 4.4 技术债分级与处理（硬约束）

- **P0（阻断交付）**：会导致数据不一致/契约不稳定/难以回滚/隐性错误的技术债 → 必须修复后再交付。
- **P1（允许交付但必须落盘）**：不会立刻炸，但会明显增加后续维护成本 → 必须在 plan 增补“后续里程碑/补测/重构点”，并写清验收方式。
- **P2（记录即可）**：小的命名/组织/易读性问题 → 记录到 plan 或后续任务列表即可。

### 4.5 复盘汇报模板（必须给用户）

在交付汇报中追加一个小节（建议标题：`Post-Dev Review`），至少包含：
- **结论**：是否建议交付（Yes/No）+ 一句话理由。
- **方案复核**：更优方案候选（至少 1 个）+ 为什么本次不做（或改做）。
- **架构与边界**：本次改动触及的边界/契约点（列出关键文件/接口）。
- **交付三问**：
  - 删掉该功能要动几个文件？（`>3` 视为耦合预警，需给降耦合计划）
  - 新增文件/类名能否一眼看懂职责？（若不能，说明重命名或降抽象动作）
  - 数据流是否单向？（若存在双向依赖，说明隔离策略与拆解时间点）
- **技术债清单（P0/P1/P2）**：每条债务给出“影响 + 处理建议 + 是否已落盘到 plan”。
- **回滚说明**：最短回滚方式（命令/开关/步骤）。

## 5) 常见反例（直接判定“不通过”）

- 只有“单元测试/接口测试”，没有覆盖主链路的 E2E 用户故事。
- E2E 用户故事只有自然语言，没有可运行的验证命令与断言。
- 宣称“完成/可用”，但没有给出任何可观测证据（退出码/输出/文件/查询结果）。
- E2E 已通过但未做“开发完成后复盘”（4.x），仍宣称完成/交付。

---

## 6) E2E 常见坑位与防漂移清单（强制执行）

> 目的：避免“做了很多但没结论”。先排除门禁漂移与环境噪声，再谈业务逻辑。

### 6.1 防漂移（endpoint / 数据源）

当你改了任一项：
- 前端图表数据源（例如 `plot_delta` → `overlay_delta`）
- 后端 endpoint/参数名
- UI 断言字段（例如 `data-*`）

必须同步更新：
- Playwright spec 的等待点与断言点（必须能观测到“命中了正确 endpoint / 正确 UI 状态”）
- plan 里的 E2E 用户故事（把断言与证据点更新到同一份真源）

**快速判别命令（建议写进日志/证据）**：
```bash
rg -n "GET /api/draw/delta|GET /api/market/candles" output/e2e_acceptance*.log
```

### 6.2 环境隔离（DB / 端口 / localStorage）

硬约束：
- 不允许“共享 DB 导致跨用例污染”而让断言漂移。
- 不允许“端口冲突导致脚本直接退出”而浪费排障时间。

推荐做法：
- 统一用非默认端口跑门禁：
  - `E2E_BACKEND_PORT=18080 E2E_FRONTEND_PORT=15180 bash scripts/e2e_acceptance.sh`
- 避免 `--reuse-servers`（除非你明确保证复用服务不会复用旧 DB/旧状态）。
- Playwright spec 必须清理 UI 持久化状态（`localStorage.clear()`），并显式写入本用例所需的 series_id/timeframe（避免默认状态不一致）。
