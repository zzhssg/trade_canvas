---
title: E2E 入口漂移（unittest / docs 命令不一致）
status: done
---

# E2E 入口漂移（unittest / docs 命令不一致）

## 背景

最近新增了一个“SQLite 最小闭环”的 E2E（closed candle → kernel → 分层落库 → adapter），并用 `unittest` 写了回归用例。

涉及文件：
- `tests/test_e2e_sqlite_pipeline.py`
- `trade_canvas/*`
- `docs/README.md`

## 具体错误（证据）

1) `python -m unittest` 默认不一定会发现测试（导致 **NO TESTS RAN**），需要显式 `discover`。
2) `docs/README.md` 中的命令曾指向 `backend/tests`，与实际测试目录不一致，导致新人按文档跑不起来。

## 影响与代价

- 误以为“有 E2E 保护”，但实际没跑到测试，回归风险升高。
- 文档误导，降低协作效率。

## 根因

- 未把“E2E 的唯一入口”当作真源管理（多个入口共存时容易漂移）。
- 新增测试后没有把运行命令写进统一门禁脚本或 docs 的唯一入口位置。

## 如何避免（检查清单）

开发前：
- [ ] 明确本次新增的 E2E 属于哪一类门禁：`python unittest` 还是 `bash scripts/e2e_acceptance.sh`（前后端联调）。
- [ ] 若新增了新的 E2E 类型，先在 `docs/README.md` 给出唯一运行命令，再写代码。

开发中：
- [ ] 本地运行一遍“会失败的用例”（至少 1 条负例）确认真的在跑。
- [ ] 避免在多个地方重复写不同的测试入口；统一收敛到一个命令/脚本。

验收时：
- [ ] `python3 -m unittest discover -s tests -p "test_*.py"` 返回 `OK`
- [ ] 如涉及联调，`bash scripts/e2e_acceptance.sh` 退出码为 0
- [ ] 跑 `bash docs/scripts/doc_audit.sh` 确保文档不漂移

## 关联

- 验证命令：
  - `python3 -m unittest discover -s tests -p "test_*.py"`
  - `bash docs/scripts/doc_audit.sh`
