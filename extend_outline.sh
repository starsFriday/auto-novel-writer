#!/usr/bin/env bash
set -euo pipefail

# 扩展大纲脚本。
# 用法：改下面几个变量，然后执行：
#   ./extend_outline.sh
#
# 例子：当前规划只有 20 章，想扩到 40 章：
#   PROJECT_ID="Urban-cultivation-in-ancient-times" TARGET_CHAPTERS=40 ./extend_outline.sh

PYTHON_BIN="${PYTHON_BIN:-python3}"
CONFIG="${CONFIG:-config.local.json}"
RUN_MODE="${RUN_MODE:-resume}"

# 要扩展大纲的项目名，对应 data/projects/<PROJECT_ID>/
PROJECT_ID="${PROJECT_ID:-Urban-cultivation-in-ancient-times}"

# 扩展后的目标总章节数。必须大于当前 novel_plan.json 里的章节数。
TARGET_CHAPTERS="${TARGET_CHAPTERS:-40}"

# 如果没有 config.local.json，就使用 config.example.json。
if [[ ! -f "$CONFIG" ]]; then
  CONFIG="config.example.json"
fi

PROJECT_DIR="data/projects/$PROJECT_ID"
PLAN_PATH="$PROJECT_DIR/novel_plan.json"
RULEBOOK_PATH="data/final/novel_rulebook.json"

if [[ ! -f "$PLAN_PATH" ]]; then
  echo "错误：未找到规划文件 $PLAN_PATH" >&2
  echo "请先用 write_from_opening.sh 生成小说规划。" >&2
  exit 2
fi

if [[ ! -f "$RULEBOOK_PATH" ]]; then
  echo "错误：未找到规则书 $RULEBOOK_PATH" >&2
  echo "请先运行：./build_rules.sh --run-mode fresh --limit-rule-novels 120" >&2
  exit 2
fi

"$PYTHON_BIN" scripts/build_writer.py \
  --config "$CONFIG" \
  --run-mode "$RUN_MODE" \
  --stage extend-plan \
  --project-id "$PROJECT_ID" \
  --target-chapters "$TARGET_CHAPTERS"
