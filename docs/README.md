# trade_canvas 文档索引

## 快速入口
- 核心说明：`docs/core/README.md`
- 开发计划：`docs/plan/README.md`
- 项目 Skills：`docs/core/skills.md`
- 复盘沉淀：`docs/复盘/README.md`
- 经验沉淀：`docs/经验/README.md`
- 运行手册（前端）：`docs/runbook/frontend.md`
- 运行手册（后端）：`docs/runbook/backend.md`

## 运行

**前端（layout MVP）**

```bash
cd frontend && npm install && npm run dev
```

**Python（freqtrade venv）**

```bash
source .env/bin/activate
freqtrade --version
```

**后端测试（pytest）**

```bash
pytest -q
```

**前后端联调 Smoke（可选）**

```bash
bash scripts/e2e_acceptance.sh
```

详细运行说明见：`docs/runbook/backend.md`、`docs/runbook/frontend.md`
