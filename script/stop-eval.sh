#!/usr/bin/env bash
# ============================================================
# WildClawBench · 停止跑批 + 清理残留任务容器
#
# 为什么需要它：框架把「删容器」放在 run_batch.py 的 finally 里，
# 强杀进程后这段不会执行 → 正在跑任务的容器会变成孤儿继续占资源。
# 所以必须「先停进程，再按镜像清容器」。
#
# 用法：
#   bash script/stop-eval.sh              # 纯 Bash 勾选菜单，无额外依赖
#   bash script/stop-eval.sh -y           # 免确认，停止全部评测进程和容器
#   bash script/stop-eval.sh --dry-run    # 只预览，不动手
#   bash script/stop-eval.sh --codex      # 容器列表只包含 Codex 镜像
#   bash script/stop-eval.sh --openclaw   # 容器列表只包含 OpenClaw 镜像
#   bash script/stop-eval.sh --astronclaw # 容器列表只包含 AstronClaw 镜像
#   bash script/stop-eval.sh --astroncode # 容器列表只包含 AstronCode 镜像
#   bash script/stop-eval.sh --opencode   # 容器列表只包含 OpenCode 镜像
#   IMAGES="img1 img2" bash script/stop-eval.sh   # 自定义镜像列表
#
# 镜像匹配：按 repo 枚举所有本地 tag（如 astroncode 的 v0.0 与 v0.1-test.8
# 同时存在时都会被清），env（DOCKER_IMAGE_*）指定的镜像额外并入。
#
# 安全说明：只展示并删除 `ancestor=<评测镜像>` 命中的容器；进程执行前
# 再次校验命令行包含 eval/run_batch.py。切勿用 docker system prune -a 代替。
# ============================================================
# Bash 3.2-4.3 considers declared empty arrays unset under `set -u`. Empty
# process/container selections are normal here, so nounset would abort before
# the script reaches the stop and cleanup steps on those Bash versions.
set -o pipefail

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

usage() {
  sed -n '2,24p' "$0"
}

for arg in "$@"; do
  case "$arg" in
    -y|--yes)   ASSUME_YES=1 ;;
    --dry-run)  DRY_RUN=1 ;;
    --codex)    SELECTED="codex" ;;
    --openclaw) SELECTED="openclaw" ;;
    --astronclaw) SELECTED="astronclaw" ;;
    --astroncode) SELECTED="astroncode" ;;
    --opencode) SELECTED="opencode" ;;
    -h|--help)  usage; exit 0 ;;
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
GRN=$'\e[32m'; RED=$'\e[31m'; YEL=$'\e[33m'; DIM=$'\e[2m'; RST=$'\e[0m'
hdr(){ echo; echo "${YEL}==== $1 ====${RST}"; }

# ── 1. 盘点跑批进程 ───────────────────────────────────────────
hdr "1/3 跑批进程"
PROC_PIDS=()
PROC_CMDS=()
while read -r pid command; do
  [ -n "${pid:-}" ] || continue
  [ "$pid" = "$$" ] && continue
  PROC_PIDS+=("$pid")
  PROC_CMDS+=("${command:-$PROC_PATTERN}")
done < <(pgrep -af "$PROC_PATTERN" 2>/dev/null || true)

if [ "${#PROC_PIDS[@]}" -eq 0 ]; then
  echo "${DIM}   无正在运行的 run_batch.py${RST}"
else
  for ((i = 0; i < ${#PROC_PIDS[@]}; i++)); do
    printf '   PID %-8s %s\n' "${PROC_PIDS[$i]}" "${PROC_CMDS[$i]}"
  done
fi

# ── 2. 盘点评测容器 ───────────────────────────────────────────
hdr "2/3 评测容器（按镜像过滤）"
CONTAINER_IDS=()
CONTAINER_NAMES=()
CONTAINER_IMAGES=()
CONTAINER_STATUSES=()
for img in "${IMG_LIST[@]}"; do
  if ! docker image inspect "$img" >/dev/null 2>&1; then
    echo "${DIM}   [$img] 镜像未加载，跳过${RST}"; continue
  fi
  rows="$(docker ps -a --filter "ancestor=$img" \
    --format '{{.ID}}\t{{.Names}}\t{{.Image}}\t{{.Status}}' 2>/dev/null)"
  cnt="$(printf '%s\n' "$rows" | grep -c . || true)"
  echo "   [$img] $cnt 个容器"
  if [ "$cnt" -gt 0 ]; then
    while IFS=$'\t' read -r cid name image status; do
      [ -n "${cid:-}" ] || continue
      duplicate=0
      for existing in "${CONTAINER_IDS[@]}"; do
        [ "$existing" = "$cid" ] && duplicate=1 && break
      done
      [ "$duplicate" = "1" ] && continue
      CONTAINER_IDS+=("$cid")
      CONTAINER_NAMES+=("$name")
      CONTAINER_IMAGES+=("$image")
      CONTAINER_STATUSES+=("$status")
      printf '     %-28s %-38s %s\n' "$name" "$image" "$status"
    done <<< "$rows"
  fi
done

# ── 无事可做 ─────────────────────────────────────────────────
if [ "${#PROC_PIDS[@]}" -eq 0 ] && [ "${#CONTAINER_IDS[@]}" -eq 0 ]; then
  hdr "结果"; echo "${GRN}   无跑批进程、无残留容器，无需处理 ✅${RST}"; exit 0
fi

if [ "$DRY_RUN" = "1" ]; then
  hdr "DRY-RUN"; echo "${DIM}   仅预览，未做任何改动。去掉 --dry-run 才会真正执行。${RST}"; exit 0
fi

# ── 纯 Bash 勾选菜单 ──────────────────────────────────────────
PROC_SELECTED=()
CONTAINER_SELECTED=()
for ((i = 0; i < ${#PROC_PIDS[@]}; i++)); do PROC_SELECTED+=(0); done
for ((i = 0; i < ${#CONTAINER_IDS[@]}; i++)); do CONTAINER_SELECTED+=(0); done

set_group_selection() {
  local group="$1" value="$2" i
  if [ "$group" = "process" ]; then
    for ((i = 0; i < ${#PROC_SELECTED[@]}; i++)); do PROC_SELECTED[$i]="$value"; done
  else
    for ((i = 0; i < ${#CONTAINER_SELECTED[@]}; i++)); do CONTAINER_SELECTED[$i]="$value"; done
  fi
}

toggle_group_selection() {
  local group="$1" current=() value
  if [ "$group" = "process" ]; then current=("${PROC_SELECTED[@]}"); else current=("${CONTAINER_SELECTED[@]}"); fi
  for value in "${current[@]}"; do [ "$value" = "0" ] && next=1 && set_group_selection "$group" 1 && return; done
  set_group_selection "$group" 0
}

selected_count() {
  local count=0 value
  for value in "${PROC_SELECTED[@]}" "${CONTAINER_SELECTED[@]}"; do
    [ "$value" = "1" ] && count=$((count + 1))
  done
  echo "$count"
}

render_menu() {
  local number=1 mark i
  printf '\033[2J\033[H'
  echo "${YEL}WildClawBench 停止评测${RST}"
  echo "输入编号切换勾选（多个编号用空格或逗号分隔）；p=全部进程，c=全部容器，a=全部，n=清空，Enter=确认，q=取消"
  echo
  echo "${YEL}进程${RST}"
  if [ "${#PROC_PIDS[@]}" -eq 0 ]; then
    echo "${DIM}  无正在运行的 run_batch.py${RST}"
  else
    for ((i = 0; i < ${#PROC_PIDS[@]}; i++)); do
      mark=" "; [ "${PROC_SELECTED[$i]}" = "1" ] && mark="✓"
      printf ' %2d. [%s] PID %-8s %s\n' "$number" "$mark" "${PROC_PIDS[$i]}" "${PROC_CMDS[$i]}"
      number=$((number + 1))
    done
  fi
  echo
  echo "${YEL}容器${RST}"
  if [ "${#CONTAINER_IDS[@]}" -eq 0 ]; then
    echo "${DIM}  无评测容器${RST}"
  else
    for ((i = 0; i < ${#CONTAINER_IDS[@]}; i++)); do
      mark=" "; [ "${CONTAINER_SELECTED[$i]}" = "1" ] && mark="✓"
      printf ' %2d. [%s] %-28s %-35s %s\n' \
        "$number" "$mark" "${CONTAINER_NAMES[$i]}" "${CONTAINER_IMAGES[$i]}" "${CONTAINER_STATUSES[$i]}"
      number=$((number + 1))
    done
  fi
  echo
  echo "当前已选择 $(selected_count) 项"
}

if [ "$ASSUME_YES" = "1" ]; then
  set_group_selection process 1
  set_group_selection container 1
else
  if [ ! -t 0 ]; then
    echo "${RED}标准输入不是终端，无法打开勾选菜单；请在终端执行，或使用 -y/--dry-run。${RST}" >&2
    exit 2
  fi
  while true; do
    render_menu
    read -r -p "> " choice
    case "$choice" in
      "")
        if [ "$(selected_count)" -eq 0 ]; then
          echo "尚未勾选任何对象。"; sleep 1; continue
        fi
        break
        ;;
      p|P) toggle_group_selection process ;;
      c|C) toggle_group_selection container ;;
      a|A) set_group_selection process 1; set_group_selection container 1 ;;
      n|N) set_group_selection process 0; set_group_selection container 0 ;;
      q|Q) echo "已取消，未做任何改动。"; exit 0 ;;
      *)
        valid=1
        normalized="${choice//,/ }"
        for number in $normalized; do
          if ! [[ "$number" =~ ^[0-9]+$ ]]; then valid=0; break; fi
          if [ "$number" -ge 1 ] && [ "$number" -le "${#PROC_PIDS[@]}" ]; then
            i=$((number - 1)); PROC_SELECTED[$i]=$((1 - PROC_SELECTED[$i]))
          elif [ "$number" -gt "${#PROC_PIDS[@]}" ] && \
               [ "$number" -le $((${#PROC_PIDS[@]} + ${#CONTAINER_IDS[@]})) ]; then
            i=$((number - ${#PROC_PIDS[@]} - 1))
            CONTAINER_SELECTED[$i]=$((1 - CONTAINER_SELECTED[$i]))
          else
            valid=0; break
          fi
        done
        [ "$valid" = "1" ] || { echo "无效选择: $choice"; sleep 1; }
        ;;
    esac
  done

  render_menu
  read -r -p "确认停止并删除以上勾选对象？[y/N] " ans
  case "$ans" in
    y|Y|yes|YES) ;;
    *) echo "已取消，未做任何改动。"; exit 0 ;;
  esac
fi

# ── 3. 停进程 + 清容器 ────────────────────────────────────────
hdr "3/3 执行"

TARGET_PIDS=()
for ((i = 0; i < ${#PROC_PIDS[@]}; i++)); do
  [ "${PROC_SELECTED[$i]}" = "1" ] && TARGET_PIDS+=("${PROC_PIDS[$i]}")
done
TARGET_CIDS=()
for ((i = 0; i < ${#CONTAINER_IDS[@]}; i++)); do
  [ "${CONTAINER_SELECTED[$i]}" = "1" ] && TARGET_CIDS+=("${CONTAINER_IDS[$i]}")
done

if [ "${#TARGET_PIDS[@]}" -gt 0 ]; then
  echo "   发送 SIGTERM ..."
  for pid in "${TARGET_PIDS[@]}"; do
    command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    if [[ "$command" != *"$PROC_PATTERN"* ]]; then
      echo "${YEL}   ! PID $pid 已退出或不再是评测进程，跳过${RST}"
      continue
    fi
    kill -TERM "$pid" 2>/dev/null || true
  done
  sleep "$KILL_WAIT"
  forced=0
  for pid in "${TARGET_PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      [ "$forced" = "0" ] && echo "   仍存活，强制 SIGKILL ..."
      forced=1
      kill -KILL "$pid" 2>/dev/null || true
    fi
  done
  [ "$forced" = "1" ] && sleep 1
fi

if [ "${#TARGET_CIDS[@]}" -gt 0 ]; then
  for cid in "${TARGET_CIDS[@]}"; do
    docker rm -f "$cid" >/dev/null 2>&1 \
      && echo "${GRN}   ✓ 已删除容器 $cid${RST}" \
      || echo "${YEL}   ! 容器 $cid 已删除或删除失败${RST}"
  done
fi
[ "${#TARGET_PIDS[@]}" -eq 0 ] && [ "${#TARGET_CIDS[@]}" -eq 0 ] \
  && echo "${DIM}   未选择任何对象${RST}"

# ── 校验 ─────────────────────────────────────────────────────
hdr "校验"
left_p=0
for pid in "${TARGET_PIDS[@]}"; do
  kill -0 "$pid" 2>/dev/null && left_p=$((left_p + 1))
done
left_c=0
for cid in "${TARGET_CIDS[@]}"; do
  docker container inspect "$cid" >/dev/null 2>&1 && left_c=$((left_c + 1))
done
echo "   选中对象残留进程: $left_p   残留容器: $left_c"
if [ "$left_p" = "0" ] && [ "$left_c" = "0" ]; then
  echo "${GRN}   所选对象已清理完毕 ✅${RST}"
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
