# Prompt patterns (agent-browser)

Use these snippets as “task framing” when asking Codex to drive `agent-browser`.

## Deterministic element targeting

Ask for the snapshot+refs loop and machine-readable output:

- “用 `agent-browser` 打开 <url>，每次交互前后都 `snapshot -i --json`，只用 `@eN` refs 做 click/fill，直到完成 <目标>。把实际跑过的命令和关键 `--json` 输出摘要贴出来。”

## Quick UI repro + evidence

- “用 `agent-browser --headed` 复现 ‘<步骤>’，保存 `.tmp/` 下的截图（`screenshot --full`），必要时录 trace（`trace start/stop`），最后给出可复现命令序列。”

## Persistent login

- “用 `--profile .tmp/ab-profile` 登录一次后复用 session，避免每次走登录 UI；如果页面跳转了就重新 snapshot。”

## Parallel isolation

- “用 `--session agent1/agent2` 分别操作两个站点（或同站不同账号）并保持状态隔离。”

