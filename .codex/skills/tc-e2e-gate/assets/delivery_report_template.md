## 交付汇报（E2E 门禁）

### 本次覆盖的主链路 E2E 用例（必须）
- E2E Test file path：
- E2E Test name(s)：
- Runner（pytest/playwright/…）：
- 为什么它覆盖了“主链路”（一句话 + 指出链路段）：

### 用户故事是什么
- Persona：
- Goal：
- Entry：
- Exit：

### 流程是什么（按步骤）
1) …
2) …
3) …

### 具体场景与具体数值（必须，禁止空泛）

> 不能只写“预期成功/预期正确”。必须给出“可核对的具体值”，并说明这些值来自哪里（UI/接口响应/DB 查询/日志）。

- series_id / pair / timeframe / timezone：
- 初始可观测状态（举例：最后一根 K 线）：
  - candle_time=…
  - o/h/l/c/v=…
  - 来源（UI / HTTP / DB / WS）：
- 触发事件（举例：收盘 finalized）：
  - 触发时间（wall-clock 或 synthetic）：
  - 新 K 线（或更新）的具体值：
    - candle_time=…
    - o/h/l/c/v=…
- 结果（必须对应到主链路出口）：
  - UI：最后一根 close == …
  - HTTP：`/api/...` 返回 …（字段值/数量/排序）
  - WS：收到 `candle_closed` …（字段值）

### 产生了哪些数据
- 产物 1：位置/表名：
  - 关键字段：
  - 如何检查：
- 产物 2：…

### 有哪些证据（可复现）
- 验证命令：
  - 输出/返回码要点：
- 关键文件/查询结果：
  - 路径/SQL/截图点位：

### 未覆盖与风险（如有）
- …
