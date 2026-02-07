---
name: tc-agent-browser
description: Use `agent-browser` CLI for browser automation in trade_canvas (可替代/补充 Playwright)：跑网页 E2E 流程、登录/表单交互、等待/断言、抓取页面信息、截图/PDF；优先用 `snapshot` + ref（@e1/@e2）+ 可选 `--json` 以便 LLM 稳定定位元素。
---

# tc-agent-browser

## Overview

在本项目中用 `agent-browser` 做“可脚本化的浏览器操作”，适合替代/补充 Playwright 来快速验证页面流程、复现/定位 UI 问题，以及用 `snapshot` 的可访问性树 + refs（@e1）实现更稳定的交互定位。

## Quick Start（推荐工作流）

1) 先确保 `agent-browser` 可用（两种方式任选其一）：

- **无需全局安装（推荐给 agent/CI）**：用本 skill 自带脚本 `scripts/ab.sh`（会优先用已安装的 `agent-browser`，否则 fallback 到 `npx -y agent-browser`）。
- **全局安装（你提供的方式）**：`npm install -g agent-browser && agent-browser install`。也可用 `scripts/setup_agent_browser.sh` 一键执行。

2) 首次下载浏览器（Chromium）：

```bash
agent-browser install
```

3) LLM 最稳定的交互循环（尽量避免“猜 CSS”）：

```bash
agent-browser open https://example.com
agent-browser snapshot -i --json          # 拿到可交互元素 + refs（@e1/@e2）
# 从 snapshot 里选 ref 后执行动作：
agent-browser click @e2
agent-browser fill @e3 "test@example.com"
agent-browser wait --text "Welcome"
agent-browser snapshot -i --json          # 页面变化后重新 snapshot
agent-browser close
```

## 关键约定：refs 优先

`snapshot` 会输出可访问性树（Accessibility tree）并为元素分配 refs（例如 `@e2`）。在 agent 场景下：

- 优先：`snapshot -i` → 用 `@eN` 做 `click/fill/get/is/...`
- 其次：语义 locator：`find role|label|text ...`
- 最后：CSS/xpath 等传统 selector（更脆弱）

## 常用命令速查（够用版）

```bash
# 导航
agent-browser open <url>
agent-browser back | forward | reload

# 交互
agent-browser snapshot [-i] [--json]
agent-browser click <@ref|selector>
agent-browser fill <@ref|selector> "<text>"
agent-browser type <@ref|selector> "<text>"
agent-browser press Enter
agent-browser wait <selector|ms> | agent-browser wait --text "<t>" | agent-browser wait --url "<glob>"

# 读取/断言
agent-browser get title|url
agent-browser get text <@ref|selector>
agent-browser get value <@ref|selector>
agent-browser is visible|enabled|checked <@ref|selector>

# 产物
agent-browser screenshot [path] [--full]
agent-browser pdf <path>

# 收尾
agent-browser close
```

## 多会话 / 持久登录（避免反复走登录 UI）

- **并行/隔离**：`agent-browser --session <name> ...` 或设置 `AGENT_BROWSER_SESSION=<name>`
- **持久 profile**（保存 cookies/localStorage）：`agent-browser --profile <dir> open <url>` 或 `AGENT_BROWSER_PROFILE=<dir>`

示例：

```bash
agent-browser --profile .tmp/ab-profile open https://example.com/login
agent-browser snapshot -i
# 登录一次后，以后复用：
agent-browser --profile .tmp/ab-profile open https://example.com/dashboard
```

## 调试与证据（定位 UI 问题更快）

- 可视化：`agent-browser open <url> --headed`
- 截图：`agent-browser screenshot .tmp/ab.png --full`
- Trace：`agent-browser trace start .tmp/ab-trace.zip` / `agent-browser trace stop`
- 控制台/异常：`agent-browser console` / `agent-browser errors`

## 使用本 skill 的脚本

- `scripts/ab.sh`：统一入口（优先全局 `agent-browser`，否则用 `npx -y agent-browser`）。
- `scripts/setup_agent_browser.sh`：按需执行全局安装 + 下载 Chromium（相当于你写的两条命令）。

如果需要更“提示词模板化”的用法，读 `references/prompt-patterns.md`。
