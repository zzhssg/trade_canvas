#!/usr/bin/env bash
set -euo pipefail

repo_root="${1:-.}"
cd "$repo_root"

missing=0

check_contains() {
  local file="$1"
  local pattern="$2"
  local label="$3"
  if grep -Fq "$pattern" "$file"; then
    echo "OK: $label"
  else
    echo "MISSING: $label ($file -> $pattern)"
    missing=1
  fi
}

check_absent() {
  local file="$1"
  local pattern="$2"
  local label="$3"
  if grep -Fq "$pattern" "$file"; then
    echo "DRIFT: $label ($file -> $pattern)"
    missing=1
  else
    echo "OK: $label"
  fi
}

required_files=(
  "AGENTS.md"
  "docs/core/agent-workflow.md"
  "docs/core/skills.md"
)

for file in "${required_files[@]}"; do
  if [[ ! -f "$file" ]]; then
    echo "ERROR: missing required file: $file"
    exit 2
  fi
done

check_contains "AGENTS.md" "问题包协议（强制）" "AGENTS 问题包协议"
check_contains "AGENTS.md" '一次性提 `1-5` 个关键问题' "AGENTS 问题数量范围"
check_contains "AGENTS.md" '每题标记 `必答`/`可选`' "AGENTS 必答/可选标记"

check_contains "docs/core/agent-workflow.md" '问题包协议：一次性提 `1-5` 个关键决策问题' "workflow 问题包协议"
check_contains "docs/core/agent-workflow.md" "可选题未回复时按推荐默认继续" "workflow 可选题默认策略"

check_contains "docs/core/skills.md" '`tc-context-compact`' "skills 索引包含 tc-context-compact"
check_contains "docs/core/skills.md" '`tc-learning-loop`' "skills 索引包含 tc-learning-loop"
check_contains "docs/core/skills.md" '`tc-subagent-orchestration`' "skills 索引包含 tc-subagent-orchestration"

check_contains "AGENTS.md" '长会话或阶段切换：`tc-context-compact`' "AGENTS 场景触发 tc-context-compact"
check_contains "AGENTS.md" '交付后经验沉淀：`tc-learning-loop`' "AGENTS 场景触发 tc-learning-loop"
check_contains "AGENTS.md" '主会话拆分并行子任务：`tc-subagent-orchestration`' "AGENTS 场景触发 tc-subagent-orchestration"

check_contains "docs/core/agent-workflow.md" "### 1.6 子 session 编排（模拟子 agent）" "workflow 子 session 编排章节"

check_absent "AGENTS.md" "单问题协议（强制）" "移除过期单问题协议"
check_absent "docs/core/agent-workflow.md" "单问题协议：一次只问 1 个关键决策问题" "移除 workflow 旧单问题协议"

if [[ "$missing" -ne 0 ]]; then
  echo
  echo "workflow_consistency_audit: FAILED"
  echo "Fix: sync AGENTS.md / docs/core/agent-workflow.md / docs/core/skills.md."
  exit 1
fi

echo "workflow_consistency_audit: OK"
