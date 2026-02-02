#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: new_plan.sh \"Plan title\"" >&2
  exit 2
fi

title="$*"
date_ymd="$(date +%F)"

slug="$(printf "%s" "$title" | tr '[:upper:]' '[:lower:]' | tr ' ' '-' | tr -cd 'a-z0-9-')"
slug="$(printf "%s" "$slug" | sed 's/--*/-/g; s/^-//; s/-$//')"

plan_dir="docs/plan"
mkdir -p "$plan_dir"

file="${plan_dir}/${date_ymd}-${slug}.md"

if [[ -e "$file" ]]; then
  echo "ERROR: already exists: $file" >&2
  exit 1
fi

cat >"$file" <<EOF
---
title: ${title}
status: 草稿
owner:
created: ${date_ymd}
updated: ${date_ymd}
---

## 背景

## 目标 / 非目标

## 方案概述

## 里程碑

## 任务拆解
- [ ] 

## 风险与回滚

## 验收标准

## 变更记录
- ${date_ymd}: 创建（草稿）
EOF

echo "Created: $file"

