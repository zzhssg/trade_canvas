# trade_canvas · AGENTS.md


项目目标：从零重构一套“因子引擎 + 图表 + freqtrade 实盘接入”的干净架构，保持小步迭代、可验收、可回滚。

本文件是给 Codex CLI / agent 的仓库级协作说明，默认对本仓库全目录生效。若某个子目录需要更细的约束，可以在该目录下新增 `AGENTS.md` 覆盖（越深层优先级越高）。

## 注意事项

1、在新建文件或对本地代码文件进行操作时，始终使用utf-8编码（如果文件已是utf-8编码方式则无需刻意修改）。
2、所有的流程始终使用简体中文回复。
3、前端功能开关使用 Vite 环境变量（例如 `VITE_ENABLE_WORLD_FRAME`）。agent 必须自行在 `frontend/` 的 `.env*` / 启动脚本 / 运行环境中确认其取值，不要把“开没开”这种问题反问用户。

## 常用 skills 速查表（高频 6 个）

- `tc-planning`：任务拆解与计划（每步可验收/可回滚；必要时落盘 `docs/plan/`）
- `tc-e2e-gate`：E2E 用户故事门禁（规划/开发期间的主链路门禁）
- `tc-debug`：调试流程（可复现→定位→根因→最小修复→验证）
- `tc-verify`：统一质量门禁（禁兼容层/禁遗留双轨/禁临时债）
- `tc-acceptance-e2e`：最终交付门禁（E2E + 证据）
- `验收`：worktree 收尾 SOP（review → merge main → 删除 worktree + 文档状态推进）

### 60 秒执行快照（先选链路再开工）

- `docs-only`：`tc-planning`（可选）→ `tc-verify`（可选）→ `验收`；最小命令：`bash docs/scripts/doc_audit.sh`
- `test-only`：`tc-debug`（修回归时）→ `tc-verify` → `验收`；最小命令：`pytest -q`
- `单模块行为改动`：`tc-planning` → `tc-e2e-gate` → `tc-verify`；最小命令：`pytest -q` 或 `cd frontend && npm run build`
- `跨模块主链路改动`：`tc-planning` → `tc-e2e-gate` → `tc-verify` → `tc-acceptance-e2e` → `验收`；最小命令：`bash scripts/quality_gate.sh && bash scripts/e2e_acceptance.sh`
- `只做 worktree 收尾`：直接 `验收`；若涉及“最终上线证据”，先补跑 `tc-acceptance-e2e`
- `长会话/切任务`：`tc-context-compact`；最小动作：先落盘快照再切换会话或阶段
- `多子任务并行`：`tc-subagent-orchestration`；最小命令：`python3 scripts/subagent_orchestrator.py run --spec <spec.json>`
- `交付后经验沉淀`：`tc-learning-loop`；最小命令：`bash docs/scripts/doc_audit.sh`（更新 `docs/经验` 时）

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
- （建议）前置轻量检查：在不改代码的前提下，尽早暴露“根本跑不起来”的问题
  - Python/后端：`pytest -q --collect-only`
  - 前端/TS：`cd frontend && npx tsc -b --pretty false --noEmit`

做完以上事项，就可以向我提问了。

绝对禁止：

- ❌ 修改任何代码
- ❌ 急于给出解决方案
- ❌ 跳过搜索和理解步骤
- ❌ 不分析就推荐方案

阶段转换规则：本阶段你要向我提问。  
如果存在多个你无法抉择的方案，使用“问题包”一次性提问（1-5 个）。  
如果没有需要问我的，则直接进入下一阶段。

#### 阶段二：制定方案

声明格式：`【制定方案】`

前置条件：我明确回答了关键技术决策。

必须做的事：

- 列出变更（新增、修改、删除）的文件，简要描述每个文件的变化
- 两次设计（Design it Twice）：至少构思 2 种可行方案（A/B）并说明取舍依据（契约稳定性、回滚成本、验收成本）
- 消除重复逻辑：如果发现重复代码，必须通过复用或抽象来消除
- 确保修改后的代码符合 DRY 原则和良好的架构设计
- 新增文件规则按《结构复杂度硬约束 / 2) 新文件规则》执行
- 用“设计原则/红旗速记”做最小自检：方案里至少落 3 个 `P*` 原则、排查 5 个 `R*` 红旗（见下文速记表）

如果新发现了向我收集的关键决策，在这个阶段你还可以继续问我，直到没有不明确的问题之后，本阶段结束。  
本阶段默认不允许自动切换到下一阶段（低/中风险快通道除外，见《变更风险分级与低风险快通道》）。

#### 阶段三：执行方案

声明格式：`【执行方案】`

必须做的事：

- 严格按照选定方案实现
- 优先“定义错误不存在（Define Errors Out of Existence）”：先用类型/契约/不变量消解错误路径，再补必要兜底处理
- 注释只写不明显的信息（设计决策、意图、边界、权衡），禁止复述代码在做什么
- 修改后运行类型检查

绝对禁止：

- ❌ 提交代码（除非用户明确要求）
- ❌ 启动开发服务器

如果在这个阶段发现了拿不准的问题，请向我提问。

收到用户消息时，一般从 `【分析问题】` 阶段开始，除非用户明确指定阶段的名字。

### 提问与确认协议（提效补充）

- **问题包协议（强制）**：`【分析问题】` / `【制定方案】` 阶段一次性提 `1-5` 个关键问题；默认 2-3 个，高风险最多 5 个。
- **多选优先（强制）**：每题优先给 2-3 个互斥选项，并标注推荐项；同时写清该选择会影响的验收/回滚内容。
- **优先级标注（强制）**：每题标记 `必答`/`可选`；若可选题未回复，默认按推荐项继续推进，避免阻塞。
- **分段确认（中/高风险）**：方案输出按“架构与边界 → 数据流与契约 → 验收与回滚”分段推进，每段都可独立确认；低风险快通道可合并输出。
- **YAGNI 明确化（强制）**：每轮方案都要写“本轮不做什么、为什么不做、何时再评估”，避免范围膨胀。

问题包固定模板（建议直接复用）：

```text
【问题包】
Q1（必答）：<问题>
- 目的：<purpose>
- 约束：<constraints>
- 成功标准：<success criteria>
- 选项：A / B / C（推荐：A）
- 默认：<未回复时默认动作，仅可选题填写>
- 影响：<对验收/回滚的影响>

Q2（可选）：...
```

### 设计质量附加准则（本仓新增）

- 战略式编程优先于战术式编程：拒绝“先跑起来再说、以后再清理”成为默认路径。
- 通用性 vs 专用性：默认选择“适度通用”的接口；若必须专用实现，需在 plan 写明触发条件与淘汰条件。

### 设计原则速记（P-Card，低上下文）

- `P1` 复杂度是增量问题：优先先修小复杂度。
- `P2` 能跑不等于完成：可读、可回滚、可验收才算完成。
- `P3` 持续小投资：每轮至少做一个设计清债点。
- `P4` 深模块：接口收益应显著大于实现复杂度。
- `P5` 常用路径最简：接口先优化高频调用。
- `P6` 接口简于实现：宁可实现复杂，也不把复杂度暴露给调用方。
- `P7` 通用/专用分离：先放通用层，专用逻辑后置。
- `P8` 分层抽象分离：不同层禁止同抽象重复表达。
- `P9` 复杂度下沉：把复杂分支压到下层模块。
- `P10` 定义错误不存在：用类型/契约消除错误路径。
- `P11` 设计两次：行为变更必须 A/B 对比后落地。
- `P12` 注释写非显然信息：写意图/边界/权衡，不复述代码。
- `P13` 为阅读而设计：读路径清晰优先于写时省事。
- `P14` 增量以抽象为单位：优先交付可复用抽象，再叠功能。

### 设计红旗速记（R-Card，命中即预警）

- `R1` 浅模块：接口并未简化实现复杂度。
- `R2` 信息泄漏：同一设计决策散落多模块。
- `R3` 时间分解：按执行顺序组织代码而非按信息隐藏组织。
- `R4` 过度暴露：常用调用被迫理解低频能力。
- `R5` 透传方法：方法只做参数转发。
- `R6` 重复实现：同类非平凡逻辑多处复制。
- `R7` 通用/专用混杂：专用逻辑污染通用层。
- `R8` 联合方法：方法互相强依赖、难独立理解。
- `R9` 注释复述代码：注释无新增信息。
- `R10` 接口文档泄漏实现：调用方无需知道的实现细节出现在接口注释。
- `R11` 命名模糊/难命名：语义不准或难以命名。
- `R12` 难以描述：文档必须很长才说清。
- `R13` 非显而易见代码：行为含义难快速判断。

### 结构复杂度硬约束（强制门禁）

#### 1) 文件大小门禁

- 单个 Python 生产文件不超过 300 行（`backend/tests/` 与 `tests/` 豁免）。
- 单个 TSX 组件不超过 400 行。
- 单个 React hook 不超过 150 行。
- 若改动触及超限文件，默认先提交“结构拆分”再提交“行为变更”（两步都需可独立回滚）。

#### 2) 新文件规则

- 新增文件必须在方案中说明：所属领域包、替代哪个旧文件或为何不能扩展现有文件。
- 禁止创建少于 50 行的独立生产文件（`__init__.py`、类型/协议声明、导出聚合文件等基础骨架除外）；确需例外时，必须在 plan 记录收益、替代方案与回滚方式。
- 禁止使用 `Policy` / `Registry` / `Router` 后缀包装单个纯函数或单个 dict 转发逻辑。

#### 3) 接口约束

- 函数/构造器参数不超过 8 个；超过时必须改为 `config dataclass`（Python）或对象参数（TS）。
- 单个 dataclass（含等价配置对象）字段不超过 15 个；超过时必须按领域拆分为嵌套结构。

#### 4) 依赖方向规则

- 数据流保持单向：`ingest -> store -> factor -> overlay -> read_model -> route`。
- 禁止 `read_model` 反向依赖 `ingest`。
- 禁止 `route` 层直接操作 `store`（必须经过 service）。

#### 5) 变更影响评估（功能变更前必须回答）

- 1-2 个文件：正常推进。
- 3-5 个文件：必须在方案中解释原因、边界与回滚。
- 6+ 个文件：视为架构预警，先提交重构计划与降耦合步骤，再进入功能实现。

#### 6) 前端拆分约束

- 组件超过 400 行必须拆分（视为门禁失败）。
- 单个组件直接管理的 `useState` 不超过 5 个。
- 超过 3 个 `useEffect` 的组件必须提取自定义 hook（或等价状态机封装）。
- Zustand 单个 slice 状态字段不超过 10 个；超过时拆分 slice 或改为嵌套领域状态。
- 历史超限组件必须在对应 plan 标注拆分里程碑；在拆分完成前禁止继续叠加职责。

### 变更风险分级与低风险快通道（信任校准）

目的：让“速度与质量”不对立 —— 低/中风险改动走快通道；高风险改动维持完整三阶段门禁。

#### 风险分级（按触及范围/契约影响/回滚难度）

- **低风险**（可快通道）：
  - 仅 `docs/` 文案/排版、状态维护（不改契约语义）
  - 仅测试用例/测试数据调整（不改生产逻辑）
  - 仅样式/无行为 refactor（不改接口/不改主链路）
- **中风险**：
  - 单模块/单目录内的逻辑变更，可能影响行为，但不涉及跨模块契约/Schema
- **高风险**：
  - 跨模块联动、契约/Schema/接口变更、核心不变量调整
  - 会影响 E2E 用户故事输入输出一致性、或回滚成本高的结构性改动

#### 低风险快通道（例外条款）

允许 agent 在同一轮对话里完成 `【制定方案】` → `【执行方案】`，前提：

- 不存在需要用户拍板的关键技术决策点
- 仍遵守“原子化变更”（避免“顺手改”混入）
- 必须给出最小验收命令（写死，避免猜测）：
  - docs：`bash docs/scripts/doc_audit.sh`
  - frontend TS/样式：`cd frontend && npm run build`
  - Python/后端/测试：`pytest -q`

#### 低风险快通道执行模板（推荐直接复用）

- `docs-only`：
  1) `【制定方案】`：列出变更文档 + 回滚路径；
  2) `【执行方案】`：执行改动后跑 `bash docs/scripts/doc_audit.sh`；
  3) 交付时写 `Doc Impact: yes` + 文档路径 + 命令输出摘要。
- `test-only`：
  1) `【制定方案】`：写明“仅改测试，不改生产逻辑”的边界；
  2) `【执行方案】`：执行改动后跑 `pytest -q`（若触及前端 TS 测试，补 `cd frontend && npm run build`）；
  3) 交付时给“失败前后对比 + 命令输出摘要 + 回滚方式”。

高风险：仍必须完整走三阶段工作流；阶段二不自动切到阶段三。

#### 中风险快通道（建议条款）

允许 agent 在同一轮对话里完成 `【制定方案】` → `【执行方案】`，前提（必须全部满足）：

- 单模块/单目录内变更（不跨《多 Agent 并行开发边界》的目录所有权）
- 不涉及契约/Schema/API 变更（否则按高风险处理）
- 有现成测试覆盖或门禁可运行（至少能跑起来并在错误位置失败）
- 仍遵守原子化提交（1 commit = 1 意图，可独立回滚）

最小验收命令（按触及面选其一）：
- Python/后端：`pytest -q`
- 前端/TS：`cd frontend && npm run build`
- 联调/E2E：`bash scripts/e2e_acceptance.sh`（改动影响 FE+BE 主链路时）

## 真源文档（先看这里）

- 开发协作与架构约束：本文件（`AGENTS.md`）
- Agent 工作流（入口 / 门禁 / 证据 / 验收 SOP）：`docs/core/agent-workflow.md`
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


### 目录建议（基于当前代码，增量演进）

- `frontend/`：图表与操作台（Vite/React/TS/Tailwind）。
- `backend/app/bootstrap|core|runtime|lifecycle/`：启动装配、配置真源、运行时门禁与生命周期。
- `backend/app/pipelines|storage|factor|overlay|market|ingest/`：主写链路与市场数据链路。
- `backend/app/read_models|replay|backtest|freqtrade/`：读模型、回放、回测与外部策略适配。
- `fixtures/`：黄金数据（固定 K 线样本，用于可复现测试）。

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

## Git 提交规范（Atomic + Conventional Commits）

目标：每个 commit 只做一件事，便于 `git bisect` 定位问题与安全回滚。

### 原子化提交（Atomic Commits）

- 1 个 commit = 1 个问题 / 1 个意图；禁止“顺手改”混入无关变更
- 允许把测试/文档放在同一 commit：前提是它们**只为这一个变更服务**（不额外夹带整理）
- 任何会影响主链路契约/行为的改动：必须能被单独 `git revert <sha>` 回退

### Conventional Commits（建议格式）

- `feat(scope): <why>`
- `fix(scope): <why>`
- `refactor(scope): <why>`
- `docs(scope): <why>`
- `test(scope): <why>`

scope 建议取目录或模块：`frontend` / `backend` / `factor` / `docs` / `e2e` 等。
message 聚焦“为什么/意图”，细节放 body（可选）。

示例（5~8 条足够）：

- `fix(backend): reject signal when candle_id mismatched`
- `feat(frontend): add overlay toggle to verify ledger/overlay parity`
- `docs(core): document candle_id invariant for adapters`
- `test(e2e): cover timeframe switch without blank screen`

### 拆分 commit 的快速决策树（极简版）

- 如果一个改动无法被单独 `git revert` 回退：拆分
- 如果一个改动改变了不同验收命令的预期（例如既改后端逻辑又改前端交互）：拆分
- 如果一个改动跨越多个目录所有权边界（见《多 Agent 并行开发边界》）：优先拆分 + 引入“集成仲裁回合”

## 默认工作流（严格门禁）

详细路由流程图与两档循环（Fast loop / Delivery loop）见 `docs/core/agent-workflow.md`。

### Definition of Done（严格）

除非用户明确声明“仅文档/无行为变更”，否则默认必须满足：

- **联调 Smoke（推荐）**：涉及 FE+BE 行为变更时，至少提供 1 条可回放的联调 smoke（优先用 `tc-agent-browser` 的 `snapshot`/截图/日志作为证据；不要默认依赖 Playwright）。
- **必要测试必过**：
  - 只要改动 Python/后端：`pytest -q`
  - 只要改动前端/TS：`cd frontend && npm run build`
- **回归保护必补**：新增/修复任何行为问题时，至少补 1 条“能失败的”回归保护（unit/集成/E2E 任一即可；优先贴近主链路）。
- **证据必交付**：汇报时必须附上 `命令 + 关键输出 + 产物路径`（例如 `output/` 下的截图/日志/trace）。
- **真源一致**：`Doc Impact`、`交付三问`、文档状态推进以本节和 `docs/core/agent-workflow.md` 为唯一真源；skills 不得维护冲突版本。
- **文档/契约同步**：改了核心链路/不变量/接口契约，必须同步更新 `docs/core/` 或 `docs/core/contracts/`，并跑 `bash docs/scripts/doc_audit.sh`。
- **文档影响声明（Doc Impact）**：每个 `feat/fix/refactor` 的交付说明必须包含 `Doc Impact: yes/no`。若为 yes：列出受影响文档路径，并必须跑 `bash docs/scripts/doc_audit.sh` 作为证据。
- **回滚可行**：每一步要么可用 feature flag/开关禁用，要么能通过 `git revert` 直接回退（不接受“只能手工修复”）。
- **设计速记自检**：交付说明里至少引用 2 个 `P*`（本次采用）和 2 个 `R*`（本次排除/修复）。
- **交付三问（必须回答）**：
  - 如果删掉这个功能，需要改几个文件？（按《结构复杂度硬约束 / 5) 变更影响评估》判定）
  - 新增的文件/类命名是否一眼可懂？（若否，交付前必须重命名或补充语义）
  - 数据流是否单向？（按《结构复杂度硬约束 / 4) 依赖方向规则》自检）

### 禁止事项（硬刹车）

- 未写清“验收/证据/回滚”就大改结构或引入新链路。
- 为了赶进度破坏契约边界（“先实现再说，之后再清理”默认会变成永久技术债）。
- 无收益说明地引入超过 2 层抽象嵌套（双向依赖按《结构复杂度硬约束 / 4) 依赖方向规则》处理）。
- 没跑过上面的门禁就宣称完成/交付。

### 场景 → skills（默认触发）

常用 skills 见文件顶部速查表。完整场景映射见 `docs/core/skills.md`。

核心规则：

- **显式点名**或**任务匹配** skill 描述时，该 skill 本轮必须触发
- 跨模块/行为变更：`tc-planning` → `tc-e2e-gate`
- 调试/回归：`tc-debug`（跨模块升级 `systematic-debugging`）
- 重构/治理债收口：`tc-verify`（交付前统一质量门禁）
- 市场 K 线链路：`tc-market-kline-fastpath-v2`
- 长会话或阶段切换：`tc-context-compact`
- 需要主会话拆分并行子任务：`tc-subagent-orchestration`
- 交付后经验沉淀：`tc-learning-loop`
- **冲突裁决（按优先级）**：
  1) 开发过程主链路门禁：`tc-e2e-gate`
  2) 最终交付证据门禁：`tc-acceptance-e2e`（不替代 `tc-e2e-gate`）
  3) worktree 收尾：`验收`（全生命周期治理走 `tc-worktree-lifecycle`）
- **多 skill 推荐顺序**：`tc-planning` → `tc-e2e-gate` → `tc-verify` → `tc-acceptance-e2e` → `验收`

### 多 Agent 并行开发边界（Worktree + 目录所有权）

目标：并行时靠“模块边界隔离冲突”，冲突时人工仲裁，不靠多人互相改同一片代码。

#### 并行边界（目录所有权）

| 边界目录 | 默认负责人（Agent 角色） | 主要职责 |
|---|---|---|
| `frontend/` | UI Agent | 图表/交互/前端类型/FE E2E |
| `backend/` | API Agent | FastAPI/契约/存储/WS/HTTP |
| `trade_canvas/` | Kernel Agent | 因子内核/领域逻辑/主链路不变量 |
| `freqtrade_user_data/` | Freqtrade Adapter Agent | 策略对接、dry-run 信号、适配层 |
| `tests/` | Test Agent | pytest/集成测试/回归保护 |
| `docs/` | Docs Agent | contracts/plan/runbook/SoT |

#### 硬规则

- 一个 agent 的一个 worktree：只改自己边界内目录（除非进入“高风险变更”并明确声明要跨边界）
- 跨边界改动必须由“集成仲裁”统一合并：在交付说明中显式标注这是一次集成回合（避免责任不清）

#### 与现有能力对齐（减少猜测）

- 并行开发默认使用 `tc-worktree-lifecycle` 管理 worktree 生命周期（/dev 或 API；端口分配与元数据可追踪）
- 合并/验收推荐统一走：`bash scripts/worktree_acceptance.sh`（默认 dry-run；需要真正合并时再加 `--yes`）

#### 集成仲裁回合（交付模板，3-5 行）

当你必须跨多个边界目录联动时，交付说明至少包含：

- Integrator: <人/agent>
- Touched: `frontend/`, `backend/`, ...
- Gate: `bash scripts/e2e_acceptance.sh`（+ 是否设置 `E2E_PLAN_DOC`）
- Evidence: `output/playwright/...` + 关键输出摘要
- Rollback: `git revert <sha...>` 或开关（`VITE_ENABLE_*` / `TRADE_CANVAS_ENABLE_*`）

## Skills（触发与使用规则）

skill 是一份本地流程约定，存放在 `.codex/skills/<skill-name>/SKILL.md`。安装方式见 `docs/core/skills.md`。

触发规则：

- **显式点名**：用户写 skill 名称（例如 `tc-debug`），本轮必须触发
- **任务匹配**：请求明显匹配某个 skill 描述时，本轮必须触发
- **多技能**：选"最小覆盖集合"，说明使用顺序
- **不跨回合继承**：除非用户再次提到

使用方式：先打开 `SKILL.md`，只读到足以执行当前请求为止；优先用现成脚本/模板。
