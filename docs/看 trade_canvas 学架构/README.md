---
title: 看 trade_canvas 学架构（专栏索引）
status: done
created: 2026-02-11
updated: 2026-02-11
---

# 看 trade_canvas 学架构（专栏索引）

这个目录专门存放“高信息密度 + 白话叙事”的架构学习文章，目标是：

- 让刚学过几天 C 语言的人，也能看懂本项目的主链路设计。
- 同时学到前后端设计原则、后端架构范式、可复用的软件工程方法论。
- 所有文章都落在本仓代码事实上，避免“讲概念不落地”。

## 使用方式

- 按编号顺序阅读（00 -> 01 -> 02 ...）。
- 每篇文章都尽量对应真实代码位置，读完可直接对照源码验证。
- 新文章默认继续落在本目录，保持一文一题、可独立复述。

## 已回填文章

- `00-写作拆解-如何兼顾高知识密度强逻辑与故事性.md`
- `01-项目学习编排-从几天C语言到架构思维.md`
- `01-术语卡-forming-flags-runtime-flags.md`
- `02-用pen因子链讲透插件架构与增量算法.md`
- `03-从pen到zhongshu-anchor-讲透多插件协同状态机.md`
- `04-把可复现讲透-幂等-bootstrap-fingerprint三件套.md`
- `04-从serviceerror到runtimeflags-讲透可回滚后端治理.md`
- `05-从factor-slices到world-frame-讲透读模型一致性.md`
- `06-从runtime-flags到container-讲透控制面装配.md`
- `07-从ingestpipeline到补偿回滚-讲透故障隔离与恢复.md`
- `08-从ingestsupervisor到binance-ws-讲透实时摄取调度.md`
- `09-从ws协议到catchup机制-讲透客户端时序一致性.md`
- `10-从gap-backfill到tail-coverage-讲透历史缺口修复策略.md`
- `11-从replay-package到overlay-package-讲透回放协议与缓存键.md`
- `12-从测试边界到架构护栏-讲透用测试守住设计.md`
- `13-从依赖注入到容器边界-讲透如何避免全局状态失控.md`
- `14-从错误码到故障分层-讲透可观测错误体系怎么设计.md`
- `15-从补偿到幂等-讲透失败后再试一次为何常常不安全.md`
- `16-从window-plan到state-rebuild-limit-讲透增量因子引擎的成本护栏.md`

## 约定

- 命名建议：`<序号>-<主题>.md`
- 每篇尽量包含：
  - 为什么难（冲突）
  - 关键规则（原理）
  - 代码锚点（可验证）
  - 可复述清单（学习闭环）
