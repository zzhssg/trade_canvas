---
title: 第9关：把可复现讲透——幂等/bootstrap/fingerprint 三件套
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 第9关：把可复现讲透——幂等/bootstrap/fingerprint 三件套

前两关你学会了插件架构和多插件协同。系统能跑了，因子能算了。

但有一个隐藏的大问题：**结果可靠吗？**

- 网络抖了，同一根蜡烛被处理了两次，账本会不会多记一笔？
- 服务器重启了，内存里的状态丢了，接着算会不会算错？
- 你改了 pivot 的窗口参数，历史数据还是按旧参数算的，新旧混在一起怎么办？

这三个问题，对应三个机制：**幂等**、**bootstrap**、**fingerprint**。

它们就像银行的三道安全锁：

```text
幂等      = 同一笔转账不管提交几次，只执行一次
bootstrap = 换了柜员，新柜员能从账本恢复到上一任的工作状态
fingerprint = 银行升级了记账规则，自动把旧账本按新规则重做
```

三道锁缺一不可。这一关，我们一道一道拆开看。

---

## 1. 第一道锁：幂等——同一笔账不记两次

### 问题：重试会不会污染账本？

想象你在 ATM 转账。按了"确认"，屏幕卡住了，你不确定转没转成功，又按了一次。

如果银行系统没有防重复机制，你就转了两次钱。

因子系统也面临同样的问题：网络抖动、服务重启、补算重试，都可能让同一个事件被"再执行一次"。

### 解决：event_key + 唯一约束

每个事件都有一个唯一的"流水号"——`event_key`：

```python
# pen.confirmed 的 event_key
key = f"confirmed:{start_time}:{end_time}:{direction}"
# 例如: "confirmed:1707000000:1707003600:1"

# pivot.major 的 event_key
key = f"major:{pivot_time}:{direction}:{window}"

# zhongshu.dead 的 event_key
key = f"dead:{start_time}:{formed_time}:{death_time}:{zg:.8f}:{zd:.8f}:{formed_reason}"
```

数据库表有唯一约束：

```sql
-- backend/app/factor_store.py
CREATE TABLE IF NOT EXISTS factor_events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  series_id TEXT NOT NULL,
  factor_name TEXT NOT NULL,
  event_key TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  UNIQUE (series_id, factor_name, event_key)  -- 三元组唯一！
);
```

写入时用 `ON CONFLICT DO NOTHING`：

```python
# backend/app/factor_store.py
conn.executemany(
    """
    INSERT INTO factor_events(...)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(series_id, factor_name, event_key) DO NOTHING
    """,
    [(...) for e in events],
)
```

效果：同一个事件，不管你写几次，数据库里只有一条。就像 ATM 的防重复机制——同一笔转账，不管你按几次确认，只扣一次钱。

### event_key 的设计哲学

注意 pen 的 event_key 是 `confirmed:{start_time}:{end_time}:{direction}`，里面没有 `visible_time`。

为什么？因为 `visible_time` 是"什么时候发现这笔的"，不是"这笔是什么"。同一笔从 A 到 B 的上涨笔，不管是在 C 出现时发现的还是在 D 出现时发现的，它都是同一笔。

就像一张发票：发票号由"卖方+买方+金额"决定，不由"会计什么时候录入"决定。录入时间变了，发票还是同一张。

---

## 2. 第二道锁：Bootstrap——新柜员接手老账本

### 问题：重启后内存状态丢了怎么办？

第 7 关讲过，pen 的增量算法依赖 `effective_pivots` 这个"余额本"。它存在内存里。

服务器重启了，内存清空了，余额本没了。如果从空状态开始算，结果肯定不对——就像新会计上任，不看前任的账本，从零开始记账。

### 解决：从事件日志重建状态

系统的事件表是 append-only 的——只追加，不修改，不删除。这意味着所有历史都在。

Bootstrap 的流程就是：从事件日志里"回放"出内存状态。

```python
# backend/app/factor_rebuild_loader.py
def build_incremental_bootstrap_state(self, *, series_id, head_time, ...):
    # 第①步：从数据库捞出最近一段时间的事件
    rebuild_events = self.collect_rebuild_event_buckets(
        series_id=series_id,
        state_start=state_start,    # 往前推 lookback_candles
        head_time=head_time,        # 到上次处理的位置
        scan_limit=state_scan_limit,
    )

    # 第②步：创建空白状态
    state = _BootstrapReplayState(
        effective_pivots=[],
        confirmed_pens=[],
        zhongshu_state={},
        ...
    )

    # 第③步：按拓扑序调用每个插件的 bootstrap
    for factor_name in self._graph.topo_order:
        plugin = self._registry.require(factor_name)
        bootstrap = getattr(plugin, "bootstrap_from_history", None)
        if callable(bootstrap):
            bootstrap(series_id=series_id, state=state, runtime=self._runtime)

    # 第④步：返回重建后的状态
    return FactorBootstrapState(
        effective_pivots=state.effective_pivots,
        confirmed_pens=state.confirmed_pens,
        zhongshu_state=state.zhongshu_state,
        ...
    )
```

注意第③步：bootstrap 也按拓扑序执行。为什么？

因为 zhongshu 的 bootstrap 需要 `confirmed_pens`（pen 的产出），而 pen 的 bootstrap 需要 `effective_pivots`（pivot 的产出）。如果乱序执行，zhongshu 去读 `confirmed_pens` 的时候，pen 还没恢复，读到的是空列表。

就像新员工入职培训：先学基础（pivot），再学进阶（pen），最后学高级（zhongshu）。不能跳着学。

### 为什么不全量重算？

你可能会问：既然事件都在，为什么不从第一根蜡烛开始全量重算？

因为太慢了。如果有 10 万根蜡烛，全量重算要处理 10 万次。而 bootstrap 只需要读最近一段时间的事件（比如最近 2000 根蜡烛对应的事件），几毫秒就能恢复状态。

就像游戏存档：你不需要从第一关重新打，读取存档就能回到上次的进度。事件日志就是"自动存档"，bootstrap 就是"读档"。

---

## 3. 第三道锁：Fingerprint——升级规则后自动重做账本

### 问题：改了算法参数，历史数据怎么办？

你把 pivot 的窗口从 5 改成了 7。这意味着 pivot 的判定标准变了，之前算出来的所有 pivot、pen、zhongshu 都可能不对了。

但数据库里存的还是按窗口 5 算出来的旧数据。如果你用新代码（窗口 7）继续增量计算，新数据和旧数据的口径就不一致了——就像一本账本，前半本用人民币记，后半本用美元记，加起来毫无意义。

### 解决：指纹检测 + 自动重建

系统会给每个系列计算一个"指纹"（fingerprint），包含所有影响计算结果的要素：

```python
# backend/app/factor_fingerprint.py
def build_series_fingerprint(*, series_id, settings, graph, registry, ...):
    payload = {
        "series_id": series_id,
        "graph": list(graph.topo_order),           # 依赖图变了？
        "settings": {
            "pivot_window_major": settings.pivot_window_major,  # 参数变了？
            "pivot_window_minor": settings.pivot_window_minor,
            "lookback_candles": settings.lookback_candles,
        },
        "files": {
            "factor_orchestrator.py": _file_sha256(...),  # 代码变了？
            "pen.py": _file_sha256(...),
            "zhongshu.py": _file_sha256(...),
            # ... 所有插件文件的 SHA256
        },
    }
    raw = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(raw.encode()).hexdigest()
```

指纹包含四类要素：

| 要素 | 白话 | 变了意味着什么 |
| ---- | ---- | ---- |
| 拓扑图 | 插件的依赖关系 | 执行顺序变了 |
| 参数 | pivot 窗口、lookback 等 | 计算规则变了 |
| 代码 SHA256 | 每个插件文件的哈希 | 算法逻辑变了 |
| logic_version | 手动版本号 | 强制标记变更 |

任何一项变了，指纹就变了。

### 指纹不匹配时怎么办？

每次 `ingest_closed` 开始前，编排器会检查指纹：

```python
# backend/app/factor_orchestrator.py
current_fingerprint = self._build_series_fingerprint(series_id=series_id, settings=s)
rebuild_outcome = self._fingerprint_rebuild_coordinator().ensure_series_ready(
    series_id=series_id,
    auto_rebuild=True,
    current_fingerprint=current_fingerprint,
)
```

如果指纹不匹配，`ensure_series_ready` 会触发重建：

```python
# backend/app/factor_fingerprint_rebuild.py
def ensure_series_ready(self, *, series_id, auto_rebuild, current_fingerprint):
    current = self._factor_store.get_series_fingerprint(series_id)
    if current is not None and current.fingerprint == current_fingerprint:
        return FactorFingerprintRebuildOutcome(forced=False)  # 匹配，正常增量

    # 不匹配！触发重建
    # 1. 保留最近 N 根蜡烛（默认 2000）
    self._candle_store.trim_series_to_latest_n_in_conn(conn, series_id=series_id, keep=keep_candles)
    # 2. 清空该系列的所有因子数据
    self._factor_store.clear_series_in_conn(conn, series_id=series_id)
    # 3. 写入新指纹
    self._factor_store.upsert_series_fingerprint_in_conn(conn, series_id=series_id, fingerprint=current_fingerprint)

    return FactorFingerprintRebuildOutcome(forced=True)
```

重建后，系统会从保留的蜡烛开始，用新的算法全量重算。

### 为什么只保留最近 2000 根？

这是一个工程折中：

- 保留全部蜡烛？重算太慢，可能有几十万根。
- 只保留最近的？丢失了远古历史，但对实时交易来说够用了。

就像搬家时整理旧物：你不会把 20 年前的报纸都搬到新家，但最近几个月的重要文件一定要带上。

---

## 4. 三道锁怎么协同工作

一次完整的 `ingest_closed` 调用，三道锁的检查顺序：

```text
第①步 fingerprint 检查
  ├─ 匹配 → 继续
  └─ 不匹配 → 清空重建，更新指纹
       ↓
第②步 bootstrap 恢复
  从事件日志重建内存状态
  （如果刚重建过，事件为空，状态也为空，等于从零开始）
       ↓
第③步 增量执行
  对新蜡烛执行因子计算，产出事件
       ↓
第④步 幂等写入
  事件写入数据库，重复的自动忽略
```

三道锁缺一不可：

- 只有幂等，没有 bootstrap → 重启后状态丢失，算出来的结果不对
- 只有 bootstrap，没有 fingerprint → 改了参数后新旧口径混在一起
- 只有 fingerprint，没有幂等 → 重试时重复写入，账本膨胀

就像银行的三道防线：防重复转账（幂等）、柜员交接制度（bootstrap）、记账规则升级流程（fingerprint）。少了任何一道，系统都不可靠。

---

## 5. 一个总公式

可复现的保证可以浓缩成一个公式：

```text
同一输入 + 同一逻辑版本 + 同一调度顺序 = 同一结果
```

- "同一输入"：closed candle 是唯一权威输入
- "同一逻辑版本"：fingerprint 保证口径一致
- "同一调度顺序"：拓扑排序保证执行顺序稳定
- "同一结果"：幂等 + bootstrap 保证不管跑几次、重启几次，结果都一样

---

## 6. 代码锚点

| 概念 | 文件 | 干什么的 |
| ---- | ---- | ---- |
| 事件存储 | `backend/app/factor_store.py` | 幂等写入 + append-only |
| 指纹构建 | `backend/app/factor_fingerprint.py` | 计算口径指纹 |
| 指纹重建 | `backend/app/factor_fingerprint_rebuild.py` | 检测变更 + 触发重建 |
| 状态恢复 | `backend/app/factor_rebuild_loader.py` | bootstrap 流程 |
| 编排入口 | `backend/app/factor_orchestrator.py` | 三道锁的调用点 |

---

## 7. 过关自测

如果你能用自己的话回答这五个问题，第 9 关就过了：

1. 为什么 pen 的 event_key 不包含 visible_time？用发票号的比喻解释。
2. bootstrap 为什么必须按拓扑序执行？如果乱序会怎样？
3. fingerprint 包含哪四类要素？为什么要包含代码文件的 SHA256？
4. 指纹不匹配时，为什么只保留最近 2000 根蜡烛而不是全部？
5. 三道锁（幂等/bootstrap/fingerprint）缺了任何一道会怎样？各举一个故障场景。
