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

<!-- PLACEHOLDER_PART2 -->
