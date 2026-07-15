#!/usr/bin/env bash
# ============================================================
# WildClawBench · 评测结果「瘦身打包」
#
# 为什么需要：Codex 会把容器里整个 /tmp_workspace 快照拷进
# task_output/，于是每个任务目录都塞了一份原始输入（1GB 的视频、
# sam3.pt 权重等）。60 题 × N 模型 → eval_out 轻松涨到几十 G，
# 但真正有价值的只有评分/用量/日志/轨迹 + Agent 的交付物。
#
# 本脚本产出两个包：
#   1) *_light_*.tar.gz    —— 排除 task_output（评分/用量/日志/轨迹/汇总），通常几十 MB
#   2) *_results_*.tar.gz  —— 只含 task_output/**/results（Agent 真实交付物）
#
# 用法：
#   bash docs/local/deploy/pack-results.sh                      # 打包整个 eval_out
#   bash docs/local/deploy/pack-results.sh --scope all_suite/round1
#   bash docs/local/deploy/pack-results.sh --scope smoke/round1
#   # 只打某一轮下「指定模型」的轻量结果（不含 Agent 交付物）：
#   bash docs/local/deploy/pack-results.sh --scope all_suite/round1/xopglm52 --no-results
#   bash docs/local/deploy/pack-results.sh --no-results         # 只出轻量包，跳过 results 包
#   bash docs/local/deploy/pack-results.sh --out /tmp           # 指定输出目录
#   bash docs/local/deploy/pack-results.sh --prune              # 打包后删除 task_output 里的大媒体/权重
#   bash docs/local/deploy/pack-results.sh --dry-run            # 只看体积分布，不打包
#   EVAL_OUT=/path/to/eval_out bash docs/local/deploy/pack-results.sh
# ============================================================
set -uo pipefail

EVAL_OUT="${EVAL_OUT:-/data1/astron/claw/astronclaw-core/evaluate/astroncode-eval/eval_out}"
OUT_DIR=""
SCOPE=""
DRY_RUN=0
PRUNE=0
NO_RESULTS=0

while [ $# -gt 0 ]; do
  case "$1" in
    --scope)      SCOPE="${2:-}"; shift 2 ;;
    --out)        OUT_DIR="${2:-}"; shift 2 ;;
    --dir)        EVAL_OUT="${2:-}"; shift 2 ;;
    --prune)      PRUNE=1; shift ;;
    --no-results) NO_RESULTS=1; shift ;;
    --dry-run)    DRY_RUN=1; shift ;;
    -h|--help)    sed -n '2,32p' "$0"; exit 0 ;;
    *) echo "未知参数: $1（-h 查看用法）"; exit 1 ;;
  esac
done

GRN=$'\e[32m'; RED=$'\e[31m'; YEL=$'\e[33m'; DIM=$'\e[2m'; RST=$'\e[0m'
hdr(){ echo; echo "${YEL}==== $1 ====${RST}"; }
human(){ awk -v b="$1" 'BEGIN{s="B KB MB GB TB";split(s,a," ");i=1;while(b>=1024&&i<5){b/=1024;i++}printf "%.1f%s", b, a[i]}'; }

# 解析目标目录 TDIR：--scope 支持「相对 eval_out 的子路径」或「绝对路径」，留空则整个 eval_out
case "${SCOPE:-}" in
  /*)
    # scope 是绝对路径 → 不依赖 EVAL_OUT
    TDIR="$SCOPE"
    ;;
  *)
    [ -d "$EVAL_OUT" ] || { echo "${RED}eval_out 目录不存在: $EVAL_OUT${RST}"; echo "${DIM}（用 --dir 指定，或用 --scope 传绝对路径）${RST}"; exit 1; }
    EVAL_OUT="$(cd "$EVAL_OUT" && pwd)"      # 规范化为绝对路径
    TDIR="${SCOPE:+$EVAL_OUT/$SCOPE}"; TDIR="${TDIR:-$EVAL_OUT}"
    ;;
esac
[ -d "$TDIR" ] || { echo "${RED}目标目录不存在: $TDIR${RST}"; exit 1; }
TDIR="$(cd "$TDIR" && pwd)"                  # 规范化
PARENT="$(dirname "$TDIR")"
LEAF="$(basename "$TDIR")"                   # 归档顶层就是它（解压后只有这一层）

# 文件名标签：在 eval_out 下用相对 slug，否则用叶子名
case "$TDIR/" in
  "$EVAL_OUT/") TAG="full" ;;
  "$EVAL_OUT"/*) TAG="$(echo "${TDIR#"$EVAL_OUT"/}" | tr '/' '_')" ;;
  *) TAG="$LEAF" ;;
esac

OUT_DIR="${OUT_DIR:-$PARENT}"
TS="$(date +%Y%m%d_%H%M)"
mkdir -p "$OUT_DIR"

# 之后所有操作都以 PARENT 为工作目录、只引用 "$LEAF"：
#   → tar 归档的顶层目录就是 LEAF（解压后 = <LEAF>/具体内容），不含上面的 eval_out/all_suite/round1 各层
cd "$PARENT" || exit 1

# ── 1. 体积盘点 ───────────────────────────────────────────────
hdr "1/3 体积盘点  ($TDIR)"
total_b=$(du -sk "$LEAF" | awk '{print $1*1024}')
echo "   总体积          : $(human "$total_b")"

to_b=$(find "$LEAF" -type d -name task_output -exec du -sk {} + 2>/dev/null | awk '{s+=$1} END {print s*1024+0}')
echo "   其中 task_output: $(human "${to_b:-0}")  ${DIM}（多为原始输入副本，可排除）${RST}"

# 大媒体/权重（用 find -exec du + 而非 GNU 专有的 -printf，保证可移植）
BIG_EXPR=( -name '*.mp4' -o -name '*.mov' -o -name '*.avi' -o -name '*.mp3' -o -name '*.wav'
           -o -name '*.pt' -o -name '*.pth' -o -name '*.bin' -o -name '*.onnx' -o -name '*.ckpt' )
big_b=$(find "$LEAF" -path '*task_output*' -type f \( "${BIG_EXPR[@]}" \) -exec du -sk {} + 2>/dev/null \
        | awk '{s+=$1} END {print s*1024+0}')
echo "   其中大媒体/权重 : $(human "${big_b:-0}")  ${DIM}（--prune 可删除）${RST}"

echo "${DIM}   最大的 5 个文件：${RST}"
find "$LEAF" -type f -size +50M -exec du -sk {} + 2>/dev/null | sort -rn | head -5 \
  | while read -r kb p; do echo "     $(human "$((kb * 1024))")  $p"; done

if [ "$DRY_RUN" = "1" ]; then
  hdr "DRY-RUN"; echo "${DIM}   仅盘点，未打包。去掉 --dry-run 才会生成压缩包。${RST}"; exit 0
fi

# ── 2. 打包 ──────────────────────────────────────────────────
hdr "2/3 打包"

# 压缩器：有 pigz 就多核
if command -v pigz >/dev/null 2>&1; then
  ZIP=(pigz -p "$(nproc 2>/dev/null || echo 4)"); ZNAME="pigz(多核)"
else
  ZIP=(gzip); ZNAME="gzip"
fi
echo "${DIM}   压缩器: $ZNAME${RST}"

LIGHT="$OUT_DIR/eval_out_light_${TAG}_${TS}.tar.gz"
echo "   [1/2] 打包评分/日志/轨迹（排除 task_output；归档顶层 = ${LEAF}/）..."
tar -cf - --exclude='task_output' "$LEAF" 2>/dev/null | "${ZIP[@]}" > "$LIGHT"
[ -s "$LIGHT" ] && echo "${GRN}         ✓ $LIGHT  ($(human "$(stat -c%s "$LIGHT" 2>/dev/null || stat -f%z "$LIGHT")"))${RST}" \
                || { echo "${RED}         ✗ 打包失败${RST}"; exit 1; }

RESULTS=""
if [ "$NO_RESULTS" = "1" ]; then
  echo "   [2/2] Agent 交付物包：${DIM}已按 --no-results 跳过（只出轻量包）${RST}"
else
  RESULTS="$OUT_DIR/eval_out_results_${TAG}_${TS}.tar.gz"
  echo "   [2/2] 打包 Agent 交付物（task_output/**/results）..."
  res_dirs="$(find "$LEAF" -type d -path '*task_output*' -name results 2>/dev/null)"
  if [ -z "$res_dirs" ]; then
    echo "${DIM}         （未找到 results 目录，跳过）${RST}"; RESULTS=""
  else
    echo "$res_dirs" | tar -cf - -T - 2>/dev/null | "${ZIP[@]}" > "$RESULTS"
    echo "${GRN}         ✓ $RESULTS  ($(human "$(stat -c%s "$RESULTS" 2>/dev/null || stat -f%z "$RESULTS")"))  共 $(echo "$res_dirs" | grep -c .) 个 results 目录${RST}"
  fi
fi

# ── 3. 可选：清理大媒体 ───────────────────────────────────────
hdr "3/3 清理 task_output 里的大媒体/权重"
if [ "$PRUNE" != "1" ]; then
  echo "${DIM}   未启用（加 --prune 可释放约 $(human "${big_b:-0}")）${RST}"
else
  if [ "${big_b:-0}" -eq 0 ]; then
    echo "${DIM}   无可清理文件${RST}"
  else
    read -r -p "   确认删除 task_output 里的大媒体/权重（约 $(human "$big_b")）？评分与轨迹不受影响 [y/N] " ans
    case "$ans" in
      y|Y|yes|YES)
        find "$LEAF" -path '*task_output*' -type f \( "${BIG_EXPR[@]}" \) -delete
        after_b=$(du -sk "$LEAF" | awk '{print $1*1024}')
        echo "${GRN}   ✓ 已清理；$TDIR 体积 $(human "$total_b") → $(human "$after_b")${RST}"
        ;;
      *) echo "   已取消，未删除任何文件。" ;;
    esac
  fi
fi

# ── 汇总 ─────────────────────────────────────────────────────
hdr "完成"
echo "   产物："
echo "     $LIGHT"
[ -n "$RESULTS" ] && echo "     $RESULTS"
cat <<EOF

${DIM}下载到本地（在你的 Mac 上执行）：
  scp root@172.31.101.44:${OUT_DIR}/eval_out_*_${TS}.tar.gz .

抽查内容：
  tar -tzf ${LIGHT} | head${RST}
EOF
