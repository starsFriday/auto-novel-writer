#!/usr/bin/env bash
set -euo pipefail

# 续写小说脚本。
# 用法：改下面几个变量，然后执行：
#   ./continue_writing.sh
#
# 也可以临时用环境变量覆盖：
#   PROJECT_ID="Urban-cultivation-in-ancient-times" START_CHAPTER=21 CHAPTER_COUNT=5 ./continue_writing.sh

PYTHON_BIN="${PYTHON_BIN:-python3}"
CONFIG="${CONFIG:-config.local.json}"
RUN_MODE="${RUN_MODE:-resume}"

# 要续写的项目名，对应 data/projects/<PROJECT_ID>/
PROJECT_ID="${PROJECT_ID:-Urban-cultivation-in-ancient-times}"

# 从第几章开始续写。比如已经写完 20 章，就填 21。
START_CHAPTER="${START_CHAPTER:-21}"

# 本次续写几章。
# 设为 0 或 all：从 START_CHAPTER 一直写到 novel_plan.json 里的最后一章。
CHAPTER_COUNT="${CHAPTER_COUNT:-20}"

# 如果没有 config.local.json，就使用 config.example.json。
if [[ ! -f "$CONFIG" ]]; then
  CONFIG="config.example.json"
fi

PROJECT_DIR="data/projects/$PROJECT_ID"
PLAN_PATH="$PROJECT_DIR/novel_plan.json"

if [[ ! -f "$PLAN_PATH" ]]; then
  echo "错误：未找到规划文件 $PLAN_PATH" >&2
  echo "请先用 write_from_opening.sh 生成规划和前文。" >&2
  exit 2
fi

PLANNED_CHAPTERS="$($PYTHON_BIN -c 'import json,sys; d=json.load(open(sys.argv[1], encoding="utf-8")); print(len(d.get("chapter_plan", [])))' "$PLAN_PATH")"

if (( START_CHAPTER > PLANNED_CHAPTERS )); then
  echo "错误：当前规划只有 ${PLANNED_CHAPTERS} 章，但 START_CHAPTER=${START_CHAPTER}。" >&2
  echo "所以没有可续写的章节，脚本不会生成新内容。" >&2
  echo "如果要继续写第 ${START_CHAPTER} 章以后，需要先把 novel_plan.json 扩展到更多章节。" >&2
  exit 2
fi

echo "[continue] project=$PROJECT_ID planned_chapters=$PLANNED_CHAPTERS start_chapter=$START_CHAPTER chapter_count=$CHAPTER_COUNT"

ARGS=(
  --config "$CONFIG"
  --run-mode "$RUN_MODE"
  --stage write
  --project-id "$PROJECT_ID"
  --start-chapter "$START_CHAPTER"
)

# CHAPTER_COUNT=0/all 表示不限制数量，写到规划结束。
if [[ "$CHAPTER_COUNT" != "0" && "$CHAPTER_COUNT" != "all" ]]; then
  ARGS+=(--chapter-count "$CHAPTER_COUNT")
fi

"$PYTHON_BIN" scripts/build_writer.py "${ARGS[@]}"
