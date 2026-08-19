#!/usr/bin/env bash
# ============================================================
# WildClawBench · 切换当前分支的 Git Push 目标
#
# 用法：
#   bash script/switch-push-target.sh both    # IDEA Push 同时推送 Gitee + GitHub
#   bash script/switch-push-target.sh github  # IDEA Push 只推送 GitHub
#   bash script/switch-push-target.sh gitee   # IDEA Push 只推送公司 Gitee
#   bash script/switch-push-target.sh both --dry-run
#
# `both` 使用 origin 的多个 pushurl。Git/IDEA 对 origin 执行 push 时，
# 会依次推送到 origin 配置的全部 pushurl。
# ============================================================
set -euo pipefail

usage() {
  sed -n '2,14p' "$0"
  cat <<'EOF'

目标：both | github | gitee
选项：--branch <分支>  --dry-run  -h|--help
环境变量：GITHUB_URL、GITEE_URL 可覆盖仓库中已有远程地址
EOF
}

TARGET=""
BRANCH=""
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    both|github|gitee)
      [ -z "$TARGET" ] || { echo "只能指定一个目标: both|github|gitee" >&2; exit 1; }
      TARGET="$1"
      shift
      ;;
    --branch)
      [ $# -ge 2 ] || { echo "--branch 需要分支名" >&2; exit 1; }
      BRANCH="$2"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "未知参数: $1（-h 查看用法）" >&2
      exit 1
      ;;
  esac
done

[ -n "$TARGET" ] || { usage >&2; exit 1; }

REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || {
  echo "当前目录不在 Git 仓库中" >&2
  exit 1
}
cd "$REPO_ROOT"

if [ -z "$BRANCH" ]; then
  BRANCH="$(git symbolic-ref --quiet --short HEAD 2>/dev/null)" || {
    echo "当前处于 detached HEAD，请用 --branch 指定分支" >&2
    exit 1
  }
fi

GITHUB_URL="${GITHUB_URL:-$(git config --get remote.github.url || true)}"
GITEE_URL="${GITEE_URL:-$(git config --get remote.origin.url || true)}"
[ -n "$GITHUB_URL" ] || { echo "未找到 GitHub 地址（remote.github.url）" >&2; exit 1; }
[ -n "$GITEE_URL" ] || { echo "未找到 Gitee 地址（remote.origin.url）" >&2; exit 1; }

set_push_urls() {
  local remote="$1"
  shift
  git config --unset-all "remote.${remote}.pushurl" >/dev/null 2>&1 || true
  local url
  for url in "$@"; do
    git config --add "remote.${remote}.pushurl" "$url"
  done
}

ensure_gitee_remote() {
  if git remote get-url gitee >/dev/null 2>&1; then
    git config remote.gitee.url "$GITEE_URL"
  else
    git remote add gitee "$GITEE_URL"
  fi
  set_push_urls gitee "$GITEE_URL"
}

ensure_github_remote() {
  if git remote get-url github >/dev/null 2>&1; then
    git config remote.github.url "$GITHUB_URL"
  else
    git remote add github "$GITHUB_URL"
  fi
  set_push_urls github "$GITHUB_URL"
}

set_branch_upstream() {
  local remote="$1"
  git config "branch.${BRANCH}.remote" "$remote"
  git config "branch.${BRANCH}.merge" "refs/heads/${BRANCH}"
}

if [ "$DRY_RUN" = "1" ]; then
  case "$TARGET" in
    both)   echo "将把 ${BRANCH} 的 Push 目标切换为：公司 Gitee + GitHub" ;;
    github) echo "将把 ${BRANCH} 的 Push 目标切换为：GitHub" ;;
    gitee)  echo "将把 ${BRANCH} 的 Push 目标切换为：公司 Gitee" ;;
  esac
  echo "GitHub: $GITHUB_URL"
  echo "Gitee:  $GITEE_URL"
  exit 0
fi

ensure_github_remote
ensure_gitee_remote

case "$TARGET" in
  both)
    set_push_urls origin "$GITEE_URL" "$GITHUB_URL"
    set_branch_upstream origin
    label="公司 Gitee + GitHub"
    ;;
  github)
    set_push_urls origin "$GITHUB_URL"
    set_branch_upstream github
    label="GitHub"
    ;;
  gitee)
    set_push_urls origin "$GITEE_URL"
    set_branch_upstream gitee
    label="公司 Gitee"
    ;;
esac

echo "已切换 ${BRANCH} 的 Push 目标：${label}"
echo "当前 upstream: $(git config --get "branch.${BRANCH}.remote")/${BRANCH}"
echo "origin pushurl:"
git remote get-url --all --push origin | sed 's/^/  /'
