#!/usr/bin/env bash
# ============================================================
# WildClawBench · 停止跑批 + 清理残留任务容器
#
# 为什么需要它：框架把「删容器」放在 run_batch.py 的 finally 里，
# 强杀进程后这段不会执行 → 正在跑任务的容器会变成孤儿继续占资源。
# 所以必须「先停进程，再按镜像清容器」。
#
# 用法：
#   bash docs/local/deploy/stop-eval.sh              # 预览 + 交互确认后执行
#   bash docs/local/deploy/stop-eval.sh -y           # 免确认，直接停+清
#   bash docs/local/deploy/stop-eval.sh --dry-run    # 只预览，不动手
#   bash docs/local/deploy/stop-eval.sh --codex      # 只清 Codex 镜像的容器
#   bash docs/local/deploy/stop-eval.sh --openclaw   # 只清 OpenClaw 镜像的容器
#   bash docs/local/deploy/stop-eval.sh --astronclaw # 只清 AstronClaw 镜像的容器
#   bash docs/local/deploy/stop-eval.sh --astroncode # 只清 AstronCode 镜像的容器
#   bash docs/local/deploy/stop-eval.sh --opencode   # 只清 OpenCode 镜像的容器
#   IMAGES="img1 img2" bash docs/local/deploy/stop-eval.sh   # 自定义镜像列表
#
# 镜像匹配：按 repo 枚举所有本地 tag（如 astroncode 的 v0.0 与 v0.1-test.8
# 同时存在时都会被清），env（DOCKER_IMAGE_*）指定的镜像额外并入。
#
# 安全说明：只按 `ancestor=<评测镜像>` 过滤删除，不会碰共享服务器上
# 其它项目的镜像/容器。切勿用 `docker system prune -a` 代替本脚本。
# ============================================================
set -uo pipefail

# 各 harness 的镜像 repo；清理时涵盖该 repo 的所有本地 tag（docker 的
# ancestor 过滤不带 tag 时只匹配 :latest，所以必须逐 tag 枚举）
CODEX_REPO="wildclawbench-codex-ubuntu"
OPENCLAW_REPO="wildclawbench-ubuntu"
ASTRONCLAW_REPO="artifacts.iflytek.com/docker-private/hy-spark-agent-builder/astronclaw-core-cicd"
ASTRONCODE_REPO="wildclawbench-astroncode-ubuntu"
OPENCODE_REPO="wildclawbench-opencode-ubuntu"

# 输出：repo 的全部本地 tag + env 显式指定的镜像（可能未加载），去重
repo_images() {
  {
    docker images --format '{{.Repository}}:{{.Tag}}' 2>/dev/null \
      | grep -E "^$1:" | grep -v ':<none>$'
    [ -n "${2:-}" ] && echo "$2"
  } | sort -u
}
PROC_PATTERN="eval/run_batch.py"
KILL_WAIT="${KILL_WAIT:-5}"          # SIGTERM 后等待秒数

ASSUME_YES=0
DRY_RUN=0
SELECTED=""

for arg in "$@"; do
  case "$arg" in
    -y|--yes)   ASSUME_YES=1 ;;
    --dry-run)  DRY_RUN=1 ;;
    --codex)    SELECTED="codex" ;;
    --openclaw) SELECTED="openclaw" ;;
    --astronclaw) SELECTED="astronclaw" ;;
    --astroncode) SELECTED="astroncode" ;;
    --opencode) SELECTED="opencode" ;;
    -h|--help)  sed -n '2,23p' "$0"; exit 0 ;;
    *) echo "未知参数: $arg（-h 查看用法）"; exit 1 ;;
  esac
done

# 待清理的镜像列表（repo 全 tag 展开）
if [ -n "${IMAGES:-}" ]; then
  read -r -a IMG_LIST <<< "$IMAGES"
elif [ "$SELECTED" = "codex" ]; then
  IMG_LIST=($(repo_images "$CODEX_REPO" "${DOCKER_IMAGE_CODEX:-}"))
elif [ "$SELECTED" = "openclaw" ]; then
  IMG_LIST=($(repo_images "$OPENCLAW_REPO" "${DOCKER_IMAGE:-}"))
elif [ "$SELECTED" = "astronclaw" ]; then
  IMG_LIST=($(repo_images "$ASTRONCLAW_REPO" "${DOCKER_IMAGE_ASTRONCLAW:-}"))
elif [ "$SELECTED" = "astroncode" ]; then
  IMG_LIST=($(repo_images "$ASTRONCODE_REPO" "${DOCKER_IMAGE_ASTRONCODE:-}"))
elif [ "$SELECTED" = "opencode" ]; then
  IMG_LIST=($(repo_images "$OPENCODE_REPO" "${DOCKER_IMAGE_OPENCODE:-}"))
else
  IMG_LIST=($(repo_images "$CODEX_REPO" "${DOCKER_IMAGE_CODEX:-}") \
            $(repo_images "$OPENCLAW_REPO" "${DOCKER_IMAGE:-}") \
            $(repo_images "$ASTRONCLAW_REPO" "${DOCKER_IMAGE_ASTRONCLAW:-}") \
            $(repo_images "$ASTRONCODE_REPO" "${DOCKER_IMAGE_ASTRONCODE:-}") \
            $(repo_images "$OPENCODE_REPO" "${DOCKER_IMAGE_OPENCODE:-}"))
fi
if [ "${#IMG_LIST[@]}" -eq 0 ]; then
  echo "未发现任何评测镜像（本地无相关 repo，且未通过 env 指定），无事可做。"
  exit 0
fi

GRN=$'\e[32m'; RED=$'\e[31m'; YEL=$'\e[33m'; DIM=$'\e[2m'; RST=$'\e[0m'
hdr(){ echo; echo "${YEL}==== $1 ====${RST}"; }

# ── 1. 盘点跑批进程 ───────────────────────────────────────────
hdr "1/3 跑批进程"
PIDS="$(pgrep -f "$PROC_PATTERN" 2>/dev/null | grep -v "^$$\$" | tr '\n' ' ')"
if [ -z "${PIDS// /}" ]; then
  echo "${DIM}   无正在运行的 run_batch.py${RST}"
else
  pgrep -af "$PROC_PATTERN" 2>/dev/null | sed 's/^/   /'
fi

# ── 2. 盘点评测容器 ───────────────────────────────────────────
hdr "2/3 评测容器（按镜像过滤）"
ALL_CIDS=""
for img in "${IMG_LIST[@]}"; do
  if ! docker image inspect "$img" >/dev/null 2>&1; then
    echo "${DIM}   [$img] 镜像未加载，跳过${RST}"; continue
  fi
  cids="$(docker ps -a --filter "ancestor=$img" -q 2>/dev/null)"
  cnt="$(echo "$cids" | grep -c . || true)"
  echo "   [$img] $cnt 个容器"
  if [ "$cnt" -gt 0 ]; then
    docker ps -a --filter "ancestor=$img" --format "     {{.Names}}\t{{.Status}}" 2>/dev/null
    ALL_CIDS="$ALL_CIDS $cids"
  fi
done

# ── 无事可做 ─────────────────────────────────────────────────
if [ -z "${PIDS// /}" ] && [ -z "${ALL_CIDS// /}" ]; then
  hdr "结果"; echo "${GRN}   无跑批进程、无残留容器，无需处理 ✅${RST}"; exit 0
fi

if [ "$DRY_RUN" = "1" ]; then
  hdr "DRY-RUN"; echo "${DIM}   仅预览，未做任何改动。去掉 --dry-run 才会真正执行。${RST}"; exit 0
fi

# ── 确认 ─────────────────────────────────────────────────────
if [ "$ASSUME_YES" != "1" ]; then
  echo
  read -r -p "确认停止上述进程并删除上述容器？[y/N] " ans
  case "$ans" in
    y|Y|yes|YES) ;;
    *) echo "已取消，未做任何改动。"; exit 0 ;;
  esac
fi

# ── 3. 停进程 + 清容器 ────────────────────────────────────────
hdr "3/3 执行"

if [ -n "${PIDS// /}" ]; then
  echo "   发送 SIGTERM ..."
  pkill -f "$PROC_PATTERN" 2>/dev/null
  sleep "$KILL_WAIT"
  if pgrep -f "$PROC_PATTERN" >/dev/null 2>&1; then
    echo "   仍存活，强制 SIGKILL ..."
    pkill -9 -f "$PROC_PATTERN" 2>/dev/null
    sleep 1
  fi
  pgrep -f "$PROC_PATTERN" >/dev/null 2>&1 \
    && echo "${RED}   ✗ 仍有进程未退出，请手动检查 pgrep -af $PROC_PATTERN${RST}" \
    || echo "${GRN}   ✓ 跑批进程已终止${RST}"
fi

removed=0
for img in "${IMG_LIST[@]}"; do
  docker image inspect "$img" >/dev/null 2>&1 || continue
  cids="$(docker ps -a --filter "ancestor=$img" -q 2>/dev/null)"
  [ -z "$cids" ] && continue
  n="$(echo "$cids" | grep -c . || true)"
  echo "$cids" | xargs -r docker rm -f >/dev/null 2>&1
  removed=$((removed + n))
  echo "${GRN}   ✓ [$img] 已删除 $n 个容器${RST}"
done
[ "$removed" = "0" ] && echo "${DIM}   无容器需要删除${RST}"

# ── 校验 ─────────────────────────────────────────────────────
hdr "校验"
left_p="$(pgrep -f "$PROC_PATTERN" 2>/dev/null | wc -l | tr -d ' ')"
left_c=0
for img in "${IMG_LIST[@]}"; do
  docker image inspect "$img" >/dev/null 2>&1 || continue
  n="$(docker ps -a --filter "ancestor=$img" -q 2>/dev/null | grep -c . || true)"
  left_c=$((left_c + n))
done
echo "   残留进程: $left_p   残留容器: $left_c"
if [ "$left_p" = "0" ] && [ "$left_c" = "0" ]; then
  echo "${GRN}   全部清理完毕 ✅${RST}"
else
  echo "${RED}   仍有残留，请手动检查 ✘${RST}"; exit 1
fi

cat <<EOF

${DIM}提示：
  · 已完成任务的结果仍在 output/codex/... （score.json 等不会丢）
  · 汇总文件 summary_*.json 需整批跑完才生成，中断则没有
  · 重跑不会覆盖旧结果（目录名带随机 runid）
  · 查看中断前进度：tail -50 run_codex_<模型>.log${RST}
EOF
