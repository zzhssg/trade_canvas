#!/usr/bin/env bash
#
# 纯 git Worktree 验收脚本（不依赖 dev panel / localhost API）
#
# 目标：把 worktree 的“review → 无冲突合并 main → 删除 worktree”收敛为一个可重复执行的命令。
#
# 默认是 dry-run（只做 review + 预检查，不会 merge / remove）。
# 需要真正执行时加：--yes
#
# 推荐用法（在 feature worktree 里执行）：
#   bash scripts/worktree_acceptance.sh --yes --push
#
# 可选：合并后删除远端分支：
#   bash scripts/worktree_acceptance.sh --yes --push --delete-remote

set -euo pipefail

usage() {
  cat <<'EOF'
Usage:
  bash scripts/worktree_acceptance.sh [--yes] [--push] [--delete-remote] [--main-branch <name>] [--remote <name>] [--no-pull]
                                   [--plan-doc <path>] [--auto-doc-status] [--run-doc-audit] [--no-plan-gate]

行为说明：
  - 默认 dry-run：只输出 review 信息并做门禁检查，不会执行 merge / 删除 worktree
  - --yes：执行 merge 到 main + 删除 worktree + 删除本地分支
  - --push：在 merge 后 push main 到远端（默认 origin）
  - --delete-remote：在 merge 后删除远端分支（需要配合 --yes）
  - --no-pull：不更新 main（不 pull / 不 ff 合并远端 main）
  - --plan-doc：显式指定本次 worktree 对应的 plan 文档路径（`docs/plan/...`）
  - --auto-doc-status：在 merge 前自动把 plan 状态推进到 已上线/online，并单独提交该文档变更（需要配合 --yes）
  - --run-doc-audit：在 merge 前运行 `bash docs/scripts/doc_audit.sh`（建议交付时开启；--yes 时默认开启）
  - --no-plan-gate：显式跳过 plan 门禁（仅低风险/特例；会打印 WARN）

注意：
  - 必须在某个 worktree 内执行
  - 不允许在 main 分支的 worktree 里执行
  - feature worktree 与 main worktree 都必须是 clean（无未提交改动）
EOF
}

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1" >&2; }

yes=0
push_main=0
delete_remote=0
main_branch="main"
remote_name="origin"
no_pull=0
plan_doc=""
auto_doc_status=0
run_doc_audit=0
no_plan_gate=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) yes=1; shift ;;
    --push) push_main=1; shift ;;
    --delete-remote) delete_remote=1; shift ;;
    --main-branch) main_branch="$2"; shift 2 ;;
    --remote) remote_name="$2"; shift 2 ;;
    --no-pull) no_pull=1; shift ;;
    --plan-doc) plan_doc="$2"; shift 2 ;;
    --auto-doc-status) auto_doc_status=1; shift ;;
    --run-doc-audit) run_doc_audit=1; shift ;;
    --no-plan-gate) no_plan_gate=1; shift ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown arg: $1" >&2; usage; exit 2 ;;
  esac
done

repo_root="$(git rev-parse --show-toplevel 2>/dev/null || true)"
if [[ -z "${repo_root}" ]]; then
  log_error "当前目录不在 git 仓库内。"
  exit 2
fi

cur_branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || true)"
if [[ -z "${cur_branch}" || "${cur_branch}" == "HEAD" ]]; then
  log_error "无法识别当前分支（可能是 detached HEAD）。"
  exit 2
fi

if [[ "${cur_branch}" == "${main_branch}" ]]; then
  log_error "不允许在 ${main_branch} worktree 里执行。请在 feature worktree 里执行。"
  exit 2
fi

worktree_clean() {
  local path="$1"
  [[ -d "$path" ]] || return 2
  [[ -z "$(git -C "$path" status --porcelain 2>/dev/null || true)" ]]
}

find_worktree_path_for_branch() {
  local branch_name="$1"
  local target_ref="refs/heads/${branch_name}"
  local wt_path=""
  local wt_branch=""
  local found=""

  while IFS= read -r line || [[ -n "$line" ]]; do
    if [[ "$line" == worktree\ * ]]; then
      if [[ -n "$wt_path" && "$wt_branch" == "$target_ref" ]]; then
        found="$wt_path"
        break
      fi
      wt_path="${line#worktree }"
      wt_branch=""
      continue
    fi
    if [[ "$line" == branch\ * ]]; then
      wt_branch="${line#branch }"
      continue
    fi
  done < <(git worktree list --porcelain)

  if [[ -z "$found" && -n "$wt_path" && "$wt_branch" == "$target_ref" ]]; then
    found="$wt_path"
  fi

  echo "$found"
}

main_worktree_path="$(find_worktree_path_for_branch "${main_branch}")"
if [[ -z "${main_worktree_path}" ]]; then
  log_error "找不到 ${main_branch} 对应的 worktree。请确保本仓库有一个 worktree checkout 在 ${main_branch}。"
  exit 2
fi

log_info "=== Worktree Acceptance（纯 git）==="
log_info "Feature worktree: ${repo_root}"
log_info "Feature branch:   ${cur_branch}"
log_info "Main worktree:    ${main_worktree_path}"
log_info "Main branch:      ${main_branch}"

if ! worktree_clean "${repo_root}"; then
  log_error "Feature worktree 有未提交改动：请先提交或清理后再验收。"
  git --no-pager status -sb || true
  exit 2
fi

if ! worktree_clean "${main_worktree_path}"; then
  log_error "Main worktree 有未提交改动：请先在 main worktree 清理后再验收。"
  git -C "${main_worktree_path}" --no-pager status -sb || true
  exit 2
fi

if [[ "${auto_doc_status}" -eq 1 && "${yes}" -ne 1 ]]; then
  log_error "--auto-doc-status 需要配合 --yes（否则会在 dry-run 里产生副作用）。"
  exit 2
fi

# 默认策略：真正执行（--yes）时默认跑 doc_audit，避免“合并后才发现门禁不绿”。
if [[ "${yes}" -eq 1 && "${run_doc_audit}" -ne 1 ]]; then
  run_doc_audit=1
fi

compute_worktree_id() {
  local p="$1"
  python3 - "$p" <<'PY'
import hashlib
import sys
print(hashlib.sha256(sys.argv[1].encode()).hexdigest()[:8])
PY
}

resolve_plan_doc_from_metadata() {
  local meta_dir="$1"
  local worktree_id="$2"
  local meta_path="${meta_dir}/${worktree_id}.json"
  if [[ ! -f "${meta_path}" ]]; then
    return 0
  fi
  python3 - "${meta_path}" <<'PY'
import json
import sys
path = sys.argv[1]
try:
    data = json.load(open(path, "r", encoding="utf-8"))
except Exception:
    sys.exit(0)
val = (data.get("plan_path") or "").strip()
if val:
    print(val)
PY
}

abs_plan_path() {
  local p="$1"
  if [[ "$p" == /* ]]; then
    echo "$p"
  else
    echo "${repo_root}/${p}"
  fi
}

is_low_risk_only() {
  local f
  local ok=1
  while IFS= read -r f || [[ -n "$f" ]]; do
    [[ -z "$f" ]] && continue
    if [[ "$f" == docs/* ]] || [[ "$f" == tests/* ]] || [[ "$f" == backend/tests/* ]] || [[ "$f" == frontend/e2e/* ]]; then
      continue
    fi
    ok=0
    break
  done < <(git diff --name-only "${main_branch}...${cur_branch}" || true)
  [[ "$ok" -eq 1 ]]
}

check_plan_status_gate() {
  local path="$1"
  python3 - "$path" <<'PY'
from __future__ import annotations

import sys
from datetime import date


def read_frontmatter(path: str) -> dict[str, str]:
    with open(path, "r", encoding="utf-8") as f:
        if f.readline().strip() != "---":
            raise ValueError("missing YAML front matter (first line must be ---)")
        out: dict[str, str] = {}
        for line in f:
            s = line.rstrip("\n")
            if s.strip() == "---":
                return out
            if ":" not in s:
                continue
            k, v = s.split(":", 1)
            k = k.strip()
            v = v.strip()
            if k:
                out[k] = v
    raise ValueError("unterminated YAML front matter (missing closing ---)")


path = sys.argv[1]
meta = read_frontmatter(path)
status = (meta.get("status") or "").strip()
updated = (meta.get("updated") or "").strip()

allowed = {"done", "已完成", "online", "已上线"}
if status not in allowed:
    raise SystemExit(f"[worktree_acceptance] FAIL: {path} status must be done/已完成/online/已上线, got {status!r}")

today = date.today().isoformat()
if updated != today:
    raise SystemExit(f"[worktree_acceptance] FAIL: {path} updated must be {today}, got {updated!r}")

print(f"[worktree_acceptance] OK: plan status gate passed ({path})")
PY
}

promote_plan_status_and_commit() {
  local plan_abs="$1"
  local plan_rel="$2"

  log_info "Updating plan status: ${plan_rel} -> 已上线"
  bash docs/scripts/doc_set_status.sh 已上线 "${plan_rel}"
  git add "${plan_rel}"

  if [[ -z "$(git diff --cached --name-only)" ]]; then
    log_warn "Plan 文件没有变化（可能已是已上线且 updated=今天），跳过 docs(plan) 提交。"
    return 0
  fi

  git commit -m "docs(plan): promote to online"
  log_info "Created atomic commit: docs(plan): promote to online"
}

echo
log_info "=== Step 2: 准备 main（checkout + 可选 pull --ff-only）==="
cd "${main_worktree_path}"
git checkout "${main_branch}" >/dev/null

if [[ "${no_pull}" -ne 1 ]]; then
  if git remote get-url "${remote_name}" >/dev/null 2>&1; then
    log_info "Updating ${main_branch} from ${remote_name}/${main_branch} (ff-only)..."
    git fetch "${remote_name}" "${main_branch}" >/dev/null 2>&1 || true
    if git show-ref --verify --quiet "refs/remotes/${remote_name}/${main_branch}"; then
      git merge --ff-only "${remote_name}/${main_branch}" >/dev/null
    else
      log_warn "远端分支 refs/remotes/${remote_name}/${main_branch} 不存在，跳过 ff-only 更新。"
    fi
  else
    log_warn "远端 ${remote_name} 不存在，跳过 pull。"
  fi
else
  log_warn "--no-pull: 跳过更新 main。"
fi

cd "${repo_root}"

echo
log_info "=== Step 3: Review Gate（只读输出）==="
echo "[review] commits ( ${main_branch}..${cur_branch} )"
git --no-pager log --oneline --decorate "${main_branch}..${cur_branch}" || true
echo
echo "[review] diff --stat ( ${main_branch}...${cur_branch} )"
git --no-pager diff --stat "${main_branch}...${cur_branch}" || true
echo
echo "[review] diff --check ( ${main_branch}...${cur_branch} )"
diff_check_out="$(git diff --check "${main_branch}...${cur_branch}" || true)"
if [[ -n "${diff_check_out}" ]]; then
  echo "${diff_check_out}"
  log_error "diff --check 发现 whitespace/冲突标记问题；请先修复。"
  exit 2
else
  echo "(clean)"
fi

echo
log_info "=== Step 4: Plan Gate（中/高风险必须 plan）==="
if [[ "${no_plan_gate}" -eq 1 ]]; then
  log_warn "--no-plan-gate: 已显式跳过 plan 门禁（仅低风险/特例）。"
else
  if is_low_risk_only; then
    log_info "Low-risk only changes detected: skipping plan requirement."
  else
    # Resolve plan doc path: explicit arg > metadata (.worktree-meta) in main worktree.
    if [[ -z "${plan_doc}" ]]; then
      wt_id="$(compute_worktree_id "${repo_root}")"
      meta_dir="${main_worktree_path}/.worktree-meta"
      if [[ -d "${meta_dir}" ]]; then
        plan_doc="$(resolve_plan_doc_from_metadata "${meta_dir}" "${wt_id}" || true)"
      fi
    fi

    if [[ -z "${plan_doc}" ]]; then
      log_error "中/高风险变更必须有计划文档（docs/plan/...）。"
      log_error "请在 /dev 创建 worktree 时填写 plan_path，或在此脚本中传入：--plan-doc docs/plan/....md"
      log_error "如确为低风险/特例，可显式加：--no-plan-gate"
      exit 2
    fi

    plan_abs="$(abs_plan_path "${plan_doc}")"
    if [[ ! -f "${plan_abs}" ]]; then
      log_error "找不到 plan 文档：${plan_doc}（resolved: ${plan_abs}）"
      exit 2
    fi

    # If requested, promote plan status and commit on feature branch.
    if [[ "${yes}" -eq 1 && "${auto_doc_status}" -eq 1 ]]; then
      promote_plan_status_and_commit "${plan_abs}" "${plan_doc}"
    fi

    # Always enforce plan status gate for non-low-risk when not skipped.
    check_plan_status_gate "${plan_abs}"
  fi
fi

if [[ "${yes}" -ne 1 ]]; then
  echo
  log_warn "dry-run 模式：未执行 merge / 删除 worktree（需要真正执行请加 --yes）。"
  exit 0
fi

if [[ "${run_doc_audit}" -eq 1 && -x "docs/scripts/doc_audit.sh" ]]; then
  echo
  log_info "=== Step 5: Docs Audit Gate ==="
  bash "docs/scripts/doc_audit.sh"
fi

echo
log_info "=== Step 6: Merge Gate ==="
log_info "即将 merge: ${cur_branch} -> ${main_branch}"

merge_msg="Merge branch '${cur_branch}' (worktree acceptance)"
set +e
cd "${main_worktree_path}"
git merge --no-ff "${cur_branch}" -m "${merge_msg}"
merge_rc=$?
set -e
if [[ "${merge_rc}" -ne 0 ]]; then
  log_error "Merge 失败（可能有冲突）。已尝试回滚 merge 状态。"
  git merge --abort >/dev/null 2>&1 || true
  exit 1
fi
log_info "Merge 成功。"

if [[ "${push_main}" -eq 1 ]]; then
  log_info "Pushing ${main_branch} -> ${remote_name}/${main_branch} ..."
  git push "${remote_name}" "${main_branch}"
fi

echo
log_info "=== Step 7: 删除 worktree + 分支 ==="
log_info "Removing worktree: ${repo_root}"
git worktree remove "${repo_root}"

log_info "Deleting local branch: ${cur_branch}"
git branch -d "${cur_branch}" >/dev/null 2>&1 || log_warn "本地分支删除失败（可能仍被引用）：${cur_branch}"

if [[ "${delete_remote}" -eq 1 ]]; then
  log_info "Deleting remote branch: ${remote_name}/${cur_branch}"
  git push "${remote_name}" --delete "${cur_branch}" || log_warn "远端分支删除失败：${remote_name}/${cur_branch}"
fi

echo
log_info "=== Acceptance Complete ==="
log_info "已合并到 ${main_branch}，并删除 worktree：${repo_root}"
