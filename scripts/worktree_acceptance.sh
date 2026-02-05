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

行为说明：
  - 默认 dry-run：只输出 review 信息并做门禁检查，不会执行 merge / 删除 worktree
  - --yes：执行 merge 到 main + 删除 worktree + 删除本地分支
  - --push：在 merge 后 push main 到远端（默认 origin）
  - --delete-remote：在 merge 后删除远端分支（需要配合 --yes）
  - --no-pull：不更新 main（不 pull / 不 ff 合并远端 main）

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

while [[ $# -gt 0 ]]; do
  case "$1" in
    --yes) yes=1; shift ;;
    --push) push_main=1; shift ;;
    --delete-remote) delete_remote=1; shift ;;
    --main-branch) main_branch="$2"; shift 2 ;;
    --remote) remote_name="$2"; shift 2 ;;
    --no-pull) no_pull=1; shift ;;
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

echo
log_info "=== Step 1: Review Gate（只读输出）==="
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

echo
log_info "=== Step 3: Merge Gate ==="
log_info "即将 merge: ${cur_branch} -> ${main_branch}"
if [[ "${yes}" -ne 1 ]]; then
  log_warn "dry-run 模式：未执行 merge / 删除 worktree（需要真正执行请加 --yes）。"
  exit 0
fi

merge_msg="Merge branch '${cur_branch}' (worktree acceptance)"
set +e
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
log_info "=== Step 4: 删除 worktree + 分支 ==="
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
