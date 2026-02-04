# trade_canvas · AGENTS.md


项目目标：从零重构一套“因子引擎 + 图表 + freqtrade 实盘接入”的干净架构，保持小步迭代、可验收、可回滚。

本文件是给 Codex CLI / agent 的仓库级协作说明，默认对本仓库全目录生效。若某个子目录需要更细的约束，可以在该目录下新增 `AGENTS.md` 覆盖（越深层优先级越高）。

## 注意事项

1、在新建文件或对本地代码文件进行操作时，始终使用utf-8编码（如果文件已是utf-8编码方式则无需刻意修改）。
2、所有的流程始终使用简体中文回复。
3、前端功能开关使用 Vite 环境变量（例如 `VITE_ENABLE_WORLD_FRAME`）。agent 必须自行在 `frontend/` 的 `.env*` / 启动脚本 / 运行环境中确认其取值，不要把“开没开”这种问题反问用户。

## AI助手核心规则

### 三阶段工作流

#### 阶段一：分析问题

声明格式：`【分析问题】`

目的：因为可能存在多个可选方案，要做出正确的决策，需要足够的依据。

必须做的事：

- 理解我的意图，如果有歧义请问我
- 搜索所有相关代码
- 识别问题根因
- 主动发现问题
  - 发现重复代码
  - 识别不合理的命名
  - 发现多余的代码、类
  - 发现可能过时的设计
  - 发现过于复杂的设计、调用
  - 发现不一致的类型定义
  - 进一步搜索代码，看是否更大范围内有类似问题

做完以上事项，就可以向我提问了。

绝对禁止：

- ❌ 修改任何代码
- ❌ 急于给出解决方案
- ❌ 跳过搜索和理解步骤
- ❌ 不分析就推荐方案

阶段转换规则：本阶段你要向我提问。  
如果存在多个你无法抉择的方案，要问我，作为提问的一部分。  
如果没有需要问我的，则直接进入下一阶段。

#### 阶段二：制定方案

声明格式：`【制定方案】`

前置条件：我明确回答了关键技术决策。

必须做的事：

- 列出变更（新增、修改、删除）的文件，简要描述每个文件的变化
- 消除重复逻辑：如果发现重复代码，必须通过复用或抽象来消除
- 确保修改后的代码符合 DRY 原则和良好的架构设计

如果新发现了向我收集的关键决策，在这个阶段你还可以继续问我，直到没有不明确的问题之后，本阶段结束。  
本阶段不允许自动切换到下一阶段。

#### 阶段三：执行方案

声明格式：`【执行方案】`

必须做的事：

- 严格按照选定方案实现
- 修改后运行类型检查

绝对禁止：

- ❌ 提交代码（除非用户明确要求）
- ❌ 启动开发服务器

如果在这个阶段发现了拿不准的问题，请向我提问。

收到用户消息时，一般从 `【分析问题】` 阶段开始，除非用户明确指定阶段的名字。

## 真源文档（先看这里）

- 开发协作与架构约束：本文件（`AGENTS.md`）
- Skills 清单与安装方式：`docs/core/skills.md`
- 项目内 skills 源码：`.codex/skills/`

## 开发协作说明（agent）

### 项目介绍（15 秒版）

trade_canvas 是一个面向量化/回测/实盘接入的研究与执行工作台：以 `closed candle` 为权威输入，把同一份行情增量驱动到 **因子/策略产物（ledger）** 与 **图表叠加（overlay）**，并保持“同输入同输出”的可复现性。

成功标准（优先级从高到低）：
1) 数据与契约正确（不会“画对了但算错了 / 算对了但链路断了”）。
2) 可回放、可验收（至少 1 条端到端用户故事能跑通并留证据）。
3) 可演进（模块职责清晰、可插拔，不靠隐式全局状态）。

非目标（硬刹车）：
- 为了“快出功能”而破坏主链路契约与边界。
- 先上复杂抽象/过度过程化，再补验收与证据。

### 批判性继承：参考 trade_system（但不复刻屎山）

`trade_system` 是被废弃的老项目（代码层面不再追随），但其 `user_data/doc/Core` 有不少“可直接指导实现”的好设计，可以作为参考来源。

使用原则：
- 继承“契约/术语/不变量”，不继承“实现细节/工程负债”。
- 任何继承都要在本仓重新落盘（更短、更可测试），并配套最小 E2E 验收。

建议优先阅读：
- `../trade_system/user_data/doc/Core/核心类 2.1.md`
- `../trade_system/user_data/doc/Core/术语与坐标系（idx-time-offset）.md`
- `../trade_system/user_data/doc/Core/ARCHITECTURE.md`
- `../trade_system/user_data/doc/Core/Contracts/factor_ledger_v1.md`
- `../trade_system/user_data/doc/Core/Contracts/slot_delta_ledger_v1.md`
- `../trade_system/user_data/doc/Core/【SAD】Replay 协议总览（Package-Explain-QueryView）.md`

继承落地流程（每次只做一小步）：
1) 选一个 doc 结论（≤3 条）→ 写成 trade_canvas 的短契约（schema/接口/不变量）。
2) 实现最小闭环（mock 输入也行）→ 加一条“能失败的”验收（例如不同步时拒绝交易）。
3) 反向对拍：同一份输入重复运行，输出可复现（同输入同输出）。

### 一句话架构

- `closed candle` 是权威输入：驱动因子计算、指标展示（ledger + overlay）。
- `forming` 只用于蜡烛展示（不进因子引擎、不落库、不影响策略信号）。
- 策略与图表同源：同一根 `candle_id` 的一次 `apply_closed()` 同时产出 `ledger`（策略）与 `overlay`（绘图指令）。

### 术语与约束（必须一致）

- `candle_id`：`{symbol}:{timeframe}:{open_time}`（或等价确定性标识），所有下游对齐都用它。
- `history`：冷数据，append-only，只接受 `CandleClosed`。
- `head`：热数据，可重绘，仅用于 forming 蜡烛展示（首期可不做）。
- 禁止：在已有产物时全量重算；必须基于已有状态做增量更新（无产物才允许全量重建）。

### MVP（用户故事驱动验收）

首期只做一个端到端闭环用户故事（先 dry-run，不真下单）：
1) 系统接收一段 `CandleClosed` 序列（先用回放/mock）。
2) 因子引擎逐根增量计算，落库 event log，并产出 `ledger + overlay`。
3) 前端图表能展示蜡烛 + overlay（先 mock overlay 也可）。
4) `freqtrade` 策略通过 adapter 读取 `latest_ledger` 并产生 dry-run 信号。
5) 若 `candle_id` 不一致，策略必须拒绝出信号（fail-safe）。

### 目录建议（逐步落地，不一次性全建）

- `frontend/`：图表与操作台（Vite/React/TS/Tailwind）。
- `packages/factor_kernel/`：因子内核（只吃 closed）。
- `packages/factor_store/`：event log + snapshot（可先 sqlite/jsonl）。
- `packages/adapters/`：
  - `freqtrade_adapter/`：ledger → dataframe/信号
  - `chart_adapter/`：overlay → 前端（ws/http）
- `fixtures/`：黄金数据（固定 K 线样本，用于可复现测试）

### 运行与检查

前端：
- `cd frontend && npm install && npm run dev`
- `cd frontend && npm run build`

Python / freqtrade：
- `source .env/bin/activate`
- `freqtrade --version`

### 前端入口（快速定位）

- AppShell：`frontend/src/layout/AppShell.tsx`
- Sidebar：`frontend/src/parts/Sidebar.tsx`
- TopBar：`frontend/src/parts/TopBar.tsx`
- BottomTabs：`frontend/src/parts/BottomTabs.tsx`
- Chart：`frontend/src/widgets/ChartView.tsx`

## 默认工作流（严格门禁）

### 路由层（意图 → 角色 → 必要产出）

当用户没有显式点名 skill/角色时，先做“意图路由”，避免局部最优拖慢全局：

- 规划层·产品总监（方向/取舍）：产出 `目标 + 成功指标 + 非目标 + 风险 + 2–3 个方案对比`。
- 执行层·产品经理（需求结构化）：产出 `1 条主 E2E 用户故事 + 验收口径 + 边界条件/反例 + 最小数据样例`。
- 规划层·技术总监（架构评估）：产出 `改动范围 + 模块边界 + 契约变更点 + 2 个方案对比/取舍 + 回滚方案 + 工作量（粗）`。
- 执行层·程序员（最小实现）：产出 `最小闭环代码 + 必要测试（unit/集成/E2E）+ 证据（命令/输出/产物）`。
- 整体复盘员（“复盘”触发）：产出 `技术债/风险清单 + 文档/skill 更新建议`。

### Definition of Done（严格）

除非用户明确声明“仅文档/无行为变更”，否则默认必须满足：

- **联调 Smoke（推荐）**：涉及 FE+BE 行为变更时，至少提供 1 条可回放的联调 smoke（优先用 `tc-agent-browser` 的 `snapshot`/截图/日志作为证据；不要默认依赖 Playwright）。
- **必要测试必过**：
  - 只要改动 Python/后端：`pytest -q`
  - 只要改动前端/TS：`cd frontend && npm run build`
- **回归保护必补**：新增/修复任何行为问题时，至少补 1 条“能失败的”回归保护（unit/集成/E2E 任一即可；优先贴近主链路）。
- **证据必交付**：汇报时必须附上 `命令 + 关键输出 + 产物路径`（例如 `output/` 下的截图/日志/trace）。
- **文档/契约同步**：改了核心链路/不变量/接口契约，必须同步更新 `docs/core/` 或 `docs/core/contracts/`，并跑 `bash docs/scripts/doc_audit.sh`。
- **回滚可行**：每一步要么可用 feature flag/开关禁用，要么能通过 `git revert` 直接回退（不接受“只能手工修复”）。

### 禁止事项（硬刹车）

- 未写清“验收/证据/回滚”就大改结构或引入新链路。
- 为了赶进度破坏契约边界（“先实现再说，之后再清理”默认会变成永久技术债）。
- 没跑过上面的门禁就宣称完成/交付。

### 场景 → skills（默认触发）

下面场景默认必须启用对应 skills（除非用户明确说“不用/先不跑”）：

- **跨模块/行为变更/新增能力**：`tc-planning` → `tc-e2e-gate` →（交付）`tc-agent-browser`
- **新增/重构“领域能力”但缺少对应 skill**（例如 factor2/回放/replay）：先 `tc-planning` 写清契约/不变量/验收 → 用 `tc-skill-authoring` 创建对应 project-local skill（禁止私自丑实现）。
- **调试/回归/不稳定**：`tc-debug`
- **复杂问题的系统化调试/定位根因/设计回归实验**：`systematic-debugging`
- **需要跑真实浏览器流程**：`tc-agent-browser`
- **市场 K 线链路（HTTP/WS/ingest/落库）**：`tc-market-kline-fastpath-v2`
- **新增/修改本项目 skills**：`tc-skill-authoring`
- **前端体验/交互设计**：`ui-ux-pro-max` 或 `frontend-design`
- **图表（TradingView lightweight-charts）**：`lightweight-charts`

## Skills（触发与使用规则）

### 什么是 skill

skill 是一份本地流程约定，存放在 `SKILL.md` 中（通常在 `.codex/skills/<skill-name>/SKILL.md`）。被“触发”后，agent 必须按该 `SKILL.md` 的流程推进（包括需要跑的命令/验收/证据）。

> 说明：Codex 默认从 `$CODEX_HOME/skills/` 加载。若要让 Codex “可发现”本项目的 `.codex/skills/`，请按 `docs/core/skills.md` 执行安装脚本（例如 `bash scripts/install_project_skills.sh`）。

### Trigger rules（何时必须触发）

- **显式点名**：用户在对话中用 `$SkillName` 或直接写 skill 名称（例如 `tc-debug`），该 skill 本轮必须触发。
- **任务匹配**：用户未点名，但请求明显匹配某个 skill 的 description（例如 E2E/验收/浏览器自动化/调试/规划等），该 skill 本轮必须触发。
- **多技能**：若多个 skill 同时匹配，选择“最小覆盖集合”，并说明使用顺序。
- **不跨回合继承**：除非用户在新一轮再次提到，否则不要沿用上一轮触发的 skills。
- **缺失/不可读**：若点名的 skill 不存在/路径不可读，需要明确说明，并用最接近的流程 fallback 继续。

### How to use（渐进式加载）

1) 决定要用某个 skill 后，先打开对应 `SKILL.md`，只读到足以执行当前请求为止。  
2) 若 `SKILL.md` 指向 `assets/`、`references/`、`scripts/`，优先用现成脚本/模板，避免重复造轮子。  
3) 尽量“少猜选择器/少猜接口”：用可观测证据（命令输出、trace、截图、日志、断言）推进。
