---
title: 第14关：从 API 契约到 OpenAPI，讲透前后端怎么不吵架
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第14关：从 API 契约到 OpenAPI，讲透前后端怎么不吵架

前面你学了后端怎么写、怎么读、怎么补偿。

但系统不是后端一个人的事。前端要画图、要展示、要交互。前后端之间必须有一套"约定"，否则就是天天吵架：

- 后端说"我返回的字段叫 `at_time`"，前端说"我以为叫 `atTime`"。
- 后端悄悄加了个字段，前端没更新，页面白屏。
- 后端返回 500，前端不知道是"数据不一致"还是"服务器炸了"。

这些问题的本质都是一个：**前后端之间缺少一份双方都认可的"合同"。**

trade_canvas 这一关的核心能力，就是把这份合同写清楚、自动同步、违约就报警。

---

## 1. 先给一句总纲

前后端契约不是一份文档，而是一条自动化链路：

**后端 Pydantic 模型 → FastAPI 自动生成 OpenAPI → openapi-typescript 生成 TS 类型 → 前端编译时检查。**

任何一环断了，前后端就会"吵架"。任何一环自动化了，"吵架"就变成"编译器帮你吵"。

---

## 2. 为什么需要契约？一个没有契约的世界长什么样

想象两个人合伙开餐厅。

厨师（后端）说："今天的菜单我改了，把'红烧肉'换成了'东坡肉'。"
服务员（前端）不知道，还在跟客人说"我们有红烧肉"。
客人点了红烧肉，厨师说没有，服务员尴尬，客人生气。

问题出在哪？**菜单没有统一版本，改了也没通知。**

在软件里，这个"菜单"就是 API 契约。它规定：

- 有哪些"菜"（API 端点）；
- 每道"菜"长什么样（请求/响应的字段和类型）；
- 出了问题怎么说（错误码和错误格式）。

---

## 3. 后端怎么定义"菜单"：Pydantic 模型

trade_canvas 用 Pydantic 模型定义每个 API 的请求和响应格式。

```python
# backend/app/schemas.py
class FactorSliceV1(BaseModel):
    schema_version: int = 1                              # 版本号
    history: dict[str, Any] = Field(default_factory=dict) # 历史事件
    head: dict[str, Any] = Field(default_factory=dict)    # 当前头部
    meta: FactorMetaV1                                    # 元数据

class GetFactorSlicesResponseV1(BaseModel):
    schema_version: int = 1
    series_id: str
    at_time: int
    candle_id: str | None
    factors: list[str] = Field(default_factory=list)
    snapshots: dict[str, FactorSliceV1] = Field(default_factory=dict)
```

注意三个设计细节：

### 3.1 V1 后缀：给合同编号

每个模型名字都带 `V1` 后缀。这不是装饰，而是版本化策略。

就像租房合同有"第一版""第二版"。如果以后要改字段，不是直接改 V1，而是新建 V2。这样旧版前端还能用 V1，新版前端用 V2，两者共存。

### 3.2 schema_version 字段：合同里的版本戳

每个响应都带 `schema_version: int = 1`。前端拿到数据后可以检查这个字段：

- 如果是 1，按 V1 的规则解析；
- 如果是 2，按 V2 的规则解析；
- 如果是未知版本，提示用户升级。

就像快递包裹上的"版本标签"——拆包前先看标签，确认是你能处理的版本。

### 3.3 Field 验证：合同里的约束条款

```python
class ReplayPrepareRequestV1(BaseModel):
    series_id: str = Field(..., min_length=1)           # 不能为空
    to_time: int | None = Field(default=None, ge=0)     # 非负整数
    window_candles: int | None = Field(default=None, ge=1, le=5000)  # 1~5000
```

这些验证在请求到达业务逻辑之前就会执行。不合法的请求直接被 FastAPI 拦截，返回 422。

就像餐厅门口的保安：你点"负数份红烧肉"？对不起，进不了门。

---

## 4. 路由怎么组织：每个域一个文件，统一注册

```python
# backend/app/draw_routes.py
router = APIRouter()

@router.get("/api/draw/delta", response_model=DrawDeltaV1)
def get_draw_delta(
    series_id: str = Query(..., min_length=1),
    cursor_version_id: int = Query(0, ge=0),
    *,
    draw_read_service: DrawReadServiceDep,
) -> DrawDeltaV1:
    try:
        return draw_read_service.read_delta(...)
    except ServiceError as exc:
        raise to_http_exception(exc) from exc
```

路由的组织规则：

- **路径规范**：`/api/{域}/{资源}`，如 `/api/draw/delta`、`/api/factor/slices`、`/api/frame/live`。
- **一域一文件**：draw 的路由在 `draw_routes.py`，factor 的在 `factor_routes.py`，market 的在 `market_http_routes.py`。
- **统一注册**：所有路由在 `main.py` 里统一注册到 FastAPI app。

就像一栋办公楼：每个部门占一层楼（一个路由文件），大楼前台（main.py）统一登记所有部门。

---

## 5. 错误码体系：出了问题怎么说清楚

### 5.1 ServiceError：带编号的错误

```python
# backend/app/service_errors.py
@dataclass(frozen=True)
class ServiceError(RuntimeError):
    status_code: int    # HTTP 状态码
    detail: Any         # 错误详情（给人看的）
    code: str           # 错误编号（给机器看的）
```

错误码的命名规范是 `域.动作_失败原因`：

```python
"market.ingest_pipeline_failed"     # 市场域，写入流水线失败
"world_read.ledger_out_of_sync"     # 世界读取域，账本不同步
"backtest.strategy_not_found"       # 回测域，策略未找到
"draw_read.factor_service_not_ready" # 绘图读取域，因子服务未就绪
```

### 5.2 为什么要分 status_code、detail、code 三个字段？

因为三个字段服务三个受众：

| 字段 | 受众 | 用途 |
| ---- | ---- | ---- |
| `status_code` | HTTP 协议 | 告诉网络层"这是什么类型的错误"（404/409/500） |
| `detail` | 人类 | 告诉开发者/用户"具体出了什么问题" |
| `code` | 机器 | 告诉前端代码"该走哪个错误处理分支" |

就像医院的诊断：
- `status_code` 是科室（内科/外科/急诊）；
- `detail` 是病历描述（"左腿骨折，需要手术"）；
- `code` 是 ICD 编码（S82.0，机器可读的标准编码）。

### 5.3 路由里的错误转换

```python
except ServiceError as exc:
    raise to_http_exception(exc) from exc
```

`to_http_exception` 把 `ServiceError` 转成 FastAPI 的 `HTTPException`。这一步很关键：业务层抛的是"业务错误"，HTTP 层返回的是"HTTP 错误"。两者不是一回事。

就像翻译：医生说"S82.0"（业务语言），护士翻译成"您的腿骨折了"（患者语言）。

---

## 6. 从后端到前端：自动化的类型同步链路

这是本关最值钱的设计。

### 6.1 链路全景

```text
后端 Pydantic 模型（Python）
    ↓ FastAPI 自动生成
OpenAPI JSON spec
    ↓ openapi-typescript 工具
TypeScript 类型定义（openapi.ts）
    ↓ 手动导出
前端类型别名（api.ts）
    ↓ TypeScript 编译器
编译时类型检查
```

### 6.2 第一步：FastAPI 自动生成 OpenAPI

FastAPI 会自动把所有 Pydantic 模型和路由定义转成 OpenAPI 规范（一个 JSON 文件）。你不需要手写任何 API 文档。

就像你写了一份合同（Pydantic 模型），公证处（FastAPI）自动帮你生成一份标准格式的公证书（OpenAPI spec）。

### 6.3 第二步：openapi-typescript 生成 TS 类型

`openapi-typescript` 工具读取 OpenAPI spec，自动生成 TypeScript 类型定义：

```typescript
// frontend/src/contracts/openapi.ts（自动生成，不要手改）
export interface components {
    schemas: {
        DrawDeltaV1: {
            schema_version: number;
            series_id: string;
            to_candle_id: string | null;
            // ...
        };
        // 50+ 个 schema
    };
}
```

### 6.4 第三步：前端导出类型别名

```typescript
// frontend/src/contracts/api.ts
import type { components } from "./openapi";

export type DrawDeltaV1 = components["schemas"]["DrawDeltaV1"];
export type FactorSliceV1 = components["schemas"]["FactorSliceV1"];
export type WorldStateV1 = components["schemas"]["WorldStateV1"];
// 40+ 个类型导出
```

这一层的意义是：前端代码不直接依赖自动生成的文件结构，而是通过别名层解耦。如果自动生成的格式变了，只需要改这一个文件。

### 6.5 最终效果：后端改字段，前端编译报错

假设后端把 `at_time` 改成了 `aligned_time`：

1. Pydantic 模型变了；
2. OpenAPI spec 自动更新；
3. openapi-typescript 重新生成 TS 类型；
4. 前端所有用到 `at_time` 的地方编译报错。

**"吵架"从运行时提前到了编译时。** 编译时发现问题，比用户看到白屏发现问题，成本低一万倍。

---

## 7. 契约文档：合同的"附件"

除了代码级的类型同步，trade_canvas 还维护了一套人类可读的契约文档：

```text
docs/core/contracts/
├── README.md              # 契约索引与维护规则
├── factor_v1.md           # 因子外壳：history/head 分离
├── draw_delta_v1.md       # 绘图增量协议
├── world_state_v1.md      # 世界状态帧
├── replay_package_v1.md   # 回放包存储协议
└── ... 共 16 份契约文档
```

维护规则写得很明确：

1. 变更契约字段时，必须同步更新对应 API 文档。
2. 引入新高风险行为时，必须提供 `TRADE_CANVAS_ENABLE_*` 开关作为 kill-switch。
3. 影响核心契约的变更，必须跑 `doc_audit.sh` 并提交证据。

这些文档不是"写了没人看"的摆设。它们是"合同的附件"——当代码级的类型同步告诉你"字段类型是 int"时，契约文档告诉你"这个 int 的语义是什么、边界是什么、为什么这样设计"。

---

## 8. 前端怎么调 API：类型安全的 fetch

```typescript
// frontend/src/lib/api.ts
export async function apiJson<T>(path: string, init?: RequestInit): Promise<T> {
    const res = await fetch(apiUrl(path), {
        ...init,
        headers: { "content-type": "application/json", ...(init?.headers ?? {}) },
    });
    if (!res.ok) {
        const text = await res.text().catch(() => "");
        throw new Error(text || `HTTP ${res.status}`);
    }
    return (await res.json()) as T;
}
```

调用时指定泛型类型：

```typescript
const slices = await apiJson<GetFactorSlicesResponseV1>("/api/factor/slices?...");
// slices.candle_id  ← TypeScript 知道这是 string | null
// slices.snapshots  ← TypeScript 知道这是 Record<string, FactorSliceV1>
```

如果你写 `slices.candleId`（驼峰），TypeScript 编译器会立刻报错：`Property 'candleId' does not exist`。

就像你签了合同，合同上写的是"红烧肉"，你非要点"东坡肉"，系统直接拦住你。

---

## 9. 运行时开关：合同里的"特别条款"

有些 API 行为不是"永远开着"的，而是受运行时开关控制：

```python
# 读取 /api/market/candles 时
if bool(runtime_flags.enable_market_auto_tail_backfill):
    runtime.backfill.ensure_tail_coverage(...)
```

这意味着：同一个 API 端点，开关开着和关着，行为可能不同。

为什么要这样？

因为有些功能是"高风险"的。比如"读取时自动回补历史数据"——如果回补逻辑有 bug，可能把数据库打爆。所以先用开关控制，观察一段时间没问题再全量放开。

就像新菜上菜单：先在"隐藏菜单"里试运行，老客户可以点，确认没问题再放到正式菜单。

这些开关本身也是契约的一部分——前端需要知道"这个功能可能没开"，后端需要在文档里说明"这个开关影响哪些 API 行为"。

---

## 10. 这套设计背后的五条工程原则

```text
原则1：Single Source of Truth（唯一真源）
  → Pydantic 模型是唯一真源，OpenAPI 和 TS 类型都从它派生
  → 不是"后端写一份，前端写一份"，而是"后端写一份，前端自动同步"

原则2：Compile-time over Runtime（编译时优于运行时）
  → 类型错误在编译时发现，不是在用户看到白屏时发现
  → 成本差距：编译时修复 1 分钟，线上修复 1 小时

原则3：Structured Errors（结构化错误）
  → 错误不是一个字符串，而是 status_code + detail + code 三元组
  → 机器能路由，人类能理解

原则4：Versioned Evolution（版本化演进）
  → V1 后缀 + schema_version 字段，支持多版本共存
  → 新版本不破坏旧客户端

原则5：Contract as Code + Doc（契约即代码 + 文档）
  → 代码级契约（Pydantic → OpenAPI → TS）保证类型安全
  → 文档级契约（contracts/*.md）保证语义清晰
  → 两者互补，缺一不可
```

---

## 11. 代码锚点（按阅读顺序）

| 概念 | 文件 | 干什么的 |
| ---- | ---- | ---- |
| Pydantic 模型 | `backend/app/schemas.py` | 请求/响应的唯一真源 |
| 错误体系 | `backend/app/service_errors.py` | ServiceError + to_http_exception |
| 路由示例 | `backend/app/draw_routes.py` | 路由组织 + 错误转换 |
| FastAPI 入口 | `backend/app/main.py` | 路由注册 + OpenAPI 配置 |
| OpenAPI 类型 | `frontend/src/contracts/openapi.ts` | 自动生成的 TS 类型 |
| 类型别名 | `frontend/src/contracts/api.ts` | 前端类型导出层 |
| API 基础设施 | `frontend/src/lib/api.ts` | apiUrl + apiJson 封装 |
| 契约文档 | `docs/core/contracts/README.md` | 契约索引与维护规则 |
| 运行时开关 | `backend/app/runtime_flags.py` | API 行为开关 |

---

## 12. 过关自测

1. 为什么 Pydantic 模型要带 `V1` 后缀？如果以后要改字段，应该怎么做？
2. `schema_version` 字段和 `V1` 后缀有什么区别？各自解决什么问题？
3. 错误码为什么要分 `status_code`、`detail`、`code` 三个字段？各服务谁？
4. 从后端改一个字段到前端编译报错，中间经过了哪几步自动化？
5. 契约文档和代码级类型同步各自解决什么问题？为什么两者缺一不可？

能把这 5 题讲清楚，你就理解了"前后端契约"不是一份文档，而是一条从 Python 到 TypeScript 的自动化链路。
