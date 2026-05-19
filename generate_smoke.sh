#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
CONFIG="${CONFIG:-config.smoke.json}"

"$PYTHON_BIN" scripts/build_writer.py \
  --config "$CONFIG" \
  --stage all \
  --limit-files 4 \
  --limit-rule-novels 4 \
  --limit-rule-cards 4 \
  --target-chapters 2 \
  --target-chars 1600 \
  --chapter-count 1 \
  --opening "${OPENING:-雨夜里，失业的档案修复师林照收到一只没有寄件人的铁盒。盒里只有半张旧车票，和一行正在慢慢变淡的字：今晚十二点以前，别让任何人想起你。}"
