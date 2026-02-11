---
title: 第10关：从 IngestPipeline 到补偿回滚——讲透故障隔离与恢复
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第10关：从 IngestPipeline 到补偿回滚——讲透故障隔离与恢复

前三关你学会了"怎么正确算"——插件架构、多插件协同、幂等/bootstrap/fingerprint。

但真实世界不是教科书。网络会断、磁盘会满、代码会有 bug。**算崩了怎么办？**

这就像你学会了做菜，但厨房着火了怎么办？不是说"别着火"就行了——你得有灭火器、有逃生路线、有事后清理方案。

这一关，我们讲系统的"消防体系"。

---

## 1. 先看问题：一次写入为什么会"半成功"

一次 `ingest_closed`（写入一根收盘蜡烛）不是一个原子操作。它分三步：

```text
第①步              第②步              第③步
存蜡烛到数据库  →  跑因子计算  →  跑覆盖层计算
(store)           (factor)        (overlay)
```

如果第①步成功了，第②步崩了，会怎样？

- 数据库里多了一根新蜡烛（第①步的产物）
- 但因子没算（第②步没完成）
- 覆盖层也没算（第③步没开始）

这就是"半成功"状态——数据不一致。就像你往银行存了钱（第①步），但系统崩了没更新余额（第②步），你的存折和实际余额对不上了。

**为什么不用数据库事务把三步包成一个原子操作？**

因为这三步涉及不同的存储（蜡烛库、因子库、覆盖层库），而且因子计算可能很耗时。把它们包在一个大事务里，锁的时间太长，会拖垮整个系统。

所以系统选择了另一条路：**不追求原子性，而是追求可补偿性。**

---

## 2. IngestPipeline：把黑盒拆成透明的流水线

### 问题：出了错，怎么知道错在哪？

如果整个写入是一个黑盒函数，崩了只能看到一个 `RuntimeError("something went wrong")`。你不知道是存蜡烛崩了、还是算因子崩了、还是算覆盖层崩了。

就像医院急诊：病人说"我不舒服"，医生需要知道是头疼、肚子疼还是腿疼，才能对症下药。

### 解决：步骤化 + 结构化错误

`IngestPipeline` 把写入拆成三个明确的步骤，每步都记录结果：

```python
# backend/app/pipelines/ingest_pipeline.py
@dataclass(frozen=True)
class IngestStepResult:
    name: str           # 步骤名，如 "store.upsert_many_closed:BTCUSDT:1h"
    ok: bool            # 成功还是失败
    duration_ms: int    # 花了多久
    error: str | None = None  # 失败原因
```

三步执行的核心代码：

```python
# backend/app/pipelines/ingest_pipeline.py（简化版）
def _run_sync(self, *, series_batches, ...):
    steps = []
    rebuilt_series = set()

    for series_id in sorted(up_to_by_series.keys()):
        new_candle_times = []

        # === 第①步：存蜡烛 ===
        if matched_batch is not None:
            existing_times = store.existing_closed_times_in_conn(...)  # 先查已有的
            store.upsert_many_closed_in_conn(...)                     # 再写入
            new_candle_times = [t for t in candle_times if t not in existing_times]
            steps.append(IngestStepResult(name="store.upsert_many_closed:..."))

        # === 第②步：跑因子 ===
        if factor_orchestrator is not None:
            result = factor_orchestrator.ingest_closed(...)
            if result.rebuilt:
                rebuilt_series.add(series_id)  # 记住哪些系列被重建了
            steps.append(IngestStepResult(name="factor.ingest_closed:..."))

        # === 第③步：跑覆盖层 ===
        if overlay_orchestrator is not None:
            if series_id in rebuilt_series:
                overlay_orchestrator.reset_series(...)  # 重建过的要先清空
            overlay_orchestrator.ingest_closed(...)
            steps.append(IngestStepResult(name="overlay.ingest_closed:..."))
```

注意第③步的一个细节：如果因子刚被重建过（fingerprint 不匹配触发了重算），覆盖层必须先 `reset_series` 再重算。否则覆盖层里还残留着旧口径的数据，新旧混在一起。

就像你重新装修了房子（因子重建），但没清理旧家具（覆盖层残留），新沙发和旧茶几放在一起，风格不搭。

---

## 3. 结构化错误：病历不是一句"不舒服"

### 问题：普通异常信息不够用

`RuntimeError("factor calculation failed")` 告诉你的信息太少了。运维人员需要知道：

- 崩在哪一步？
- 影响了哪个数据序列？
- 系统有没有自动补偿？
- 补偿成功了吗？

### 解决：IngestPipelineError——带病历的异常

```python
# backend/app/pipelines/ingest_pipeline.py
class IngestPipelineError(RuntimeError):
    def __init__(self, *,
        step: str,                    # 崩在哪一步
        series_id: str,               # 影响哪个序列
        cause: BaseException,         # 原始错误
        compensated: bool = False,    # 有没有补偿
        overlay_compensated: bool = False,     # 覆盖层有没有重置
        candle_compensated_rows: int = 0,      # 回滚了几根蜡烛
        compensation_error: BaseException | None = None,  # 补偿本身有没有出错
    ):
        # 错误消息自动拼接所有信息
        suffix = ":compensated" if self.compensated else ""
        if self.overlay_compensated:
            suffix = f"{suffix}:overlay_reset"
        if self.candle_compensated_rows > 0:
            suffix = f"{suffix}:candle_rows:{self.candle_compensated_rows}"
        super().__init__(f"ingest_pipeline_failed:{step}:{series_id}:{cause}{suffix}")
```

这就像医院的病历：不是写"病人不舒服"，而是写"左腿骨折，已打石膏，石膏固定成功"。每个字段都有明确含义，方便后续诊断和追踪。

错误消息的例子：

```text
ingest_pipeline_failed:factor.ingest_closed:BTCUSDT:1h:ZeroDivisionError:compensated:candle_rows:3
```

一眼就能看出：因子计算崩了，影响的是 BTCUSDT 1小时线，原因是除零错误，系统已自动回滚了 3 根新蜡烛。

---

## 4. 补偿回滚：灭火不能把整栋楼拆了

### 问题：崩了之后怎么清理？

第①步存了蜡烛，第②步因子崩了。数据库里多了几根"没被因子处理过"的蜡烛。怎么办？

最粗暴的做法：按时间范围删除所有蜡烛。但这太危险了——可能误删历史数据。

就像厨房着火了，你不能把整栋楼炸掉来灭火。你只需要用灭火器对准着火的那口锅。

### 解决：最小破坏原则——只撤销本次新增

系统在写入蜡烛之前，先记住"哪些是已经存在的"：

```python
# 写入前：查出已有的蜡烛时间
existing_times = store.existing_closed_times_in_conn(
    conn, series_id=series_id, candle_times=candle_times,
)

# 写入后：算出哪些是本次新增的
new_candle_times = [t for t in candle_times if t not in existing_times]
```

如果后续步骤崩了，只删除 `new_candle_times`，不动历史数据：

```python
# backend/app/pipelines/ingest_pipeline.py
def _rollback_new_candles(self, *, series_id, new_candle_times):
    if not self._candle_compensate_on_error:
        return 0, None          # 开关没开，不补偿
    if not new_candle_times:
        return 0, None          # 没有新增，不用补偿
    deleted = store.delete_closed_times_in_conn(
        conn, series_id=series_id, candle_times=new_candle_times,
    )
    return deleted, None        # 返回删了几根
```

这就是"最小破坏原则"：**补偿只撤销本次副作用，不回滚历史真源。**

就像你在白纸上写了几行字，发现写错了。你只擦掉刚写的那几行，不会把整张纸撕掉。

---

## 5. 两个补偿开关：灭火器不是默认打开的

### 问题：补偿本身也可能出错

补偿操作（删蜡烛、重置覆盖层）本身也可能失败。如果补偿失败了，情况可能比不补偿更糟。

就像灭火器如果喷出来的不是泡沫而是汽油，那还不如不灭。

### 解决：用开关控制补偿策略

系统提供两个独立的补偿开关，通过环境变量控制：

```python
# backend/app/runtime_flags.py
enable_ingest_compensate_overlay_error=env_bool(
    "TRADE_CANVAS_ENABLE_INGEST_COMPENSATE_OVERLAY_ERROR"
)   # 覆盖层崩了，要不要自动重置？

enable_ingest_compensate_new_candles=env_bool(
    "TRADE_CANVAS_ENABLE_INGEST_COMPENSATE_NEW_CANDLES"
)   # 因子/覆盖层崩了，要不要回滚新蜡烛？
```

这两个开关默认都是关闭的。为什么？

因为补偿是一把双刃剑：

| 场景 | 开关状态 | 理由 |
| ---- | ---- | ---- |
| 开发环境 | 全开 | 快速试错，自动清理 |
| 测试环境 | 按需开 | 验证补偿逻辑本身 |
| 生产环境 | 谨慎开 | 先观测，确认安全再放开 |

就像医院的急救药物：不是所有药都默认给。医生要根据病情判断，该用哪种、用多少剂量。

### 覆盖层补偿的完整流程

当覆盖层崩了，补偿逻辑是这样的：

```python
# backend/app/pipelines/ingest_pipeline.py（简化版）
except Exception as exc:
    overlay_compensated = False
    compensation_error = None

    # 补偿1：重置覆盖层（如果开关开了）
    if self._overlay_compensate_on_error:
        try:
            overlay_orchestrator.reset_series(series_id=series_id)
            overlay_compensated = True
        except Exception as rollback_exc:
            compensation_error = rollback_exc  # 补偿也崩了！

    # 补偿2：回滚新蜡烛（如果开关开了）
    candle_rows, candle_error = self._rollback_new_candles(
        series_id=series_id, new_candle_times=new_candle_times,
    )

    # 把所有信息打包成结构化错误
    raise IngestPipelineError(
        step="overlay.ingest_closed",
        series_id=series_id,
        cause=exc,
        compensated=bool(overlay_compensated or candle_rows > 0),
        overlay_compensated=overlay_compensated,
        candle_compensated_rows=candle_rows,
        compensation_error=compensation_error,
    )
```

注意：即使补偿本身失败了，系统也不会吞掉错误。`compensation_error` 会被记录在 `IngestPipelineError` 里，一起上报。

就像消防员灭火时受了伤，事故报告里会同时记录"火灾原因"和"消防员受伤情况"。

---

## 6. 错误上报：从流水线到 API 的信息不丢失

### 问题：错误信息怎么传到外面？

`IngestPipeline` 抛出了结构化错误，但最终面对用户的是 HTTP API。错误信息怎么从流水线内部传到 API 响应里？

### 解决：双通道上报

`MarketIngestService` 捕获 `IngestPipelineError` 后做两件事：

```python
# backend/app/market_ingest_service.py
except IngestPipelineError as exc:
    # 通道1：往 debug hub 发详细信息（给运维看）
    debug_hub.emit(
        event="write.http.ingest_candle_closed_error",
        data={
            "step": exc.step,
            "series_id": exc.series_id,
            "error": str(exc.cause),
            "compensated": exc.compensated,
            "overlay_compensated": exc.overlay_compensated,
            "candle_compensated_rows": exc.candle_compensated_rows,
            "compensation_error": str(exc.compensation_error),
        },
    )

    # 通道2：抛标准化 ServiceError（给客户端看）
    raise ServiceError(
        status_code=500,
        detail=f"ingest_pipeline_failed:{exc.step}:{exc.series_id}",
        code="market.ingest_pipeline_failed",
    )
```

两个通道各有分工：

| 通道 | 受众 | 信息量 | 用途 |
| ---- | ---- | ---- | ---- |
| debug hub | 运维/开发 | 完整（含补偿细节） | 排查问题 |
| ServiceError | 前端/客户端 | 精简（步骤+序列） | 展示错误 |

就像飞机出了故障：黑匣子记录了所有细节（debug hub），但乘客只看到"请系好安全带"的提示（ServiceError）。

---

## 7. 一个完整的故障场景走一遍

假设：写入 BTCUSDT 1小时线的一根新蜡烛，覆盖层计算时崩了。两个补偿开关都开着。

```text
第①步 store.upsert_many_closed
  → 查到 existing_times = [1707000000, 1707003600]
  → 写入 3 根蜡烛（含 1 根新的 1707007200）
  → new_candle_times = [1707007200]
  → ✅ 成功，记录 step

第②步 factor.ingest_closed
  → 因子计算正常完成，没有重建
  → ✅ 成功，记录 step

第③步 overlay.ingest_closed
  → 💥 崩了！TypeError: unsupported operand
  → 补偿1：overlay.reset_series → ✅ 成功
  → 补偿2：rollback_new_candles → 删除 1707007200 → ✅ 成功
  → 抛出 IngestPipelineError:
    step="overlay.ingest_closed"
    series_id="BTCUSDT:1h"
    compensated=True
    overlay_compensated=True
    candle_compensated_rows=1

上层 MarketIngestService:
  → debug hub 记录完整错误信息
  → 抛出 ServiceError(500, "ingest_pipeline_failed:overlay.ingest_closed:BTCUSDT:1h")
```

整个过程：崩了 → 知道崩在哪 → 自动补偿 → 补偿结果记录 → 上报给运维和客户端。没有"半成功"的脏数据留在系统里。

---

## 8. 这套故障治理的四条原则

把这一关的设计提炼成四条可迁移的原则：

```text
原则1：Fail with context（带上下文地失败）
  → 错误必须携带步骤、序列、补偿信息
  → 不是 "something went wrong"，而是 "第2步崩了，影响BTCUSDT:1h，已回滚1根蜡烛"

原则2：Compensate minimally（最小补偿）
  → 只撤销本次副作用，不误删历史
  → 不是 "DELETE WHERE time > X"，而是 "DELETE WHERE time IN (本次新增的)"

原则3：Feature-flagged recovery（可开关的恢复）
  → 补偿策略必须可开关、可回滚
  → 不是硬编码 "出错就删"，而是 "开关开了才删"

原则4：Repair as API（修复产品化）
  → 恢复流程做成 API，不靠人肉 SQL
  → 不是 "登上服务器手动删数据"，而是 "调一个接口自动修复"
```

这四条原则不只适用于量化交易系统。任何有多步写入的系统——电商下单、支付结算、数据同步——都能用。

---

## 9. 代码锚点

| 概念 | 文件 | 干什么的 |
| ---- | ---- | ---- |
| 流水线主体 | `backend/app/pipelines/ingest_pipeline.py` | 三步执行 + 补偿回滚 |
| 结构化错误 | `backend/app/pipelines/ingest_pipeline.py` | IngestPipelineError 定义 |
| 错误上报 | `backend/app/market_ingest_service.py` | 双通道：debug hub + ServiceError |
| 补偿开关 | `backend/app/runtime_flags.py` | 两个环境变量控制 |
| 流水线测试 | `backend/tests/test_ingest_pipeline.py` | 故障场景覆盖 |

---

## 10. 过关自测

如果你能用自己的话回答这五个问题，第 10 关就过了：

1. 为什么一次 ingest 不能用数据库事务包成原子操作？用"锁的时间太长"解释。
2. `IngestPipelineError` 比普通 `RuntimeError` 多了哪些信息？用"病历 vs 不舒服"的比喻解释。
3. 最小破坏原则是什么？为什么补偿只删 `new_candle_times` 而不是按时间范围全删？
4. 两个补偿开关为什么默认关闭？在什么环境下应该打开？
5. `rebuilt_series` 为什么会触发 overlay reset？用"重新装修但没清旧家具"的比喻解释。
