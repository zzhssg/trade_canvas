## E2E 用户故事（必须覆盖主流程）

### Story ID / E2E Test Case（必须）
- Story ID（建议：`YYYY-MM-DD/<topic>/<short-scenario>`）：
- 关联 Plan：`docs/plan/YYYY-MM-DD-<topic>.md`
- E2E 测试用例（必须写到具体文件 + 测试名）：
  - Test file path:
  - Test name(s):
  - Runner（pytest/playwright/…）：

### Persona / Goal
- Persona：
- Goal：

### Entry / Exit（明确入口与出口）
- Entry（触发方式/输入）：
- Exit（成功的可观测结果）：

### Concrete Scenario（必须：写“具体数值”，禁止空泛）

> 你不能只写“预期成功/预期正确”。必须写到 **可复现的具体数据点**：
> - 例如：用户打开 BTC/USDT 4h 图，最后一根 K 线 `candle_time=...`，`close=99999`；
>   之后触发一次收盘事件，产生新 K 线 `candle_time=...`，`open=10000`，并且前端追加 1 根 candle。

- Chart / Symbol:
  - series_id / pair / timeframe:
  - timezone:
- Initial State（明确数据前置）：
  - DB empty?:
  - Existing candles (at least 1) (exact values):
    - candle_time:
    - o/h/l/c/v:
- Trigger Event（明确触发点 + 时间）：
  - what happened (e.g. finalized candle arrives):
  - when (wall-clock or synthetic time):
  - new candle expected (exact values):
    - candle_time:
    - o/h/l/c/v:
- Expected UI / API observable outcome（写具体）：
  - UI: last candle close == ?
  - API: `/api/market/candles` returns last candle_time == ?
  - WS: receives `candle_closed` with candle_time == ?

### Preconditions（前置条件）
- 数据前置（fixtures / 环境变量 / 数据库初始状态）：
- 依赖服务（是否需要启动 backend/frontend；或纯本地测试即可）：

### Main Flow（主流程步骤 + 断言）

> 要求：每一步都要写断言（可运行命令/可观测输出/落盘检查），并且断言必须是“可核对的具体值”。

每一步至少包含这些字段（不满足则不算“完整”）：
- User action（用户操作：点了什么/打开了什么）
- Requests（触发了哪些接口：method + path + query/body 的关键字段）
- Backend chain（关键链路：入口 handler → service → store/side effects）
- Assertions（断言：必须包含具体值/数量/排序）
- Evidence（证据：命令 + 输出片段 + 文件/SQL/trace 路径）

1) Step:
   - User action:
   - Requests:
   - Backend chain:
   - Assertions:
   - Evidence（文件/输出片段/查询）:

2) Step:
   - User action:
   - Requests:
   - Backend chain:
   - Assertions:
   - Evidence（文件/输出片段/查询）:

3) Step:
   - User action:
   - Requests:
   - Backend chain:
   - Assertions:
   - Evidence（文件/输出片段/查询）:

### Produced Data（产生的数据）

> 列出“能定位/能查询”的关键产物。

- Tables / Files:
  - name/path:
  - keys/fields:
  - how to inspect:

### Verification Commands（必须可复制运行）

> 至少一条自动化命令；允许多条（unit/integration/e2e）。

- Command:
  - Expected（必须是具体断言的摘要，不要只写“pass”）:

### Rollback（回滚）
- 最短回滚方式（删哪些文件/恢复哪些接口/关哪个开关）：
