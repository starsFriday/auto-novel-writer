#!/usr/bin/env bash
set -euo pipefail

PYTHON_BIN="${PYTHON_BIN:-python3}"
CONFIG="${CONFIG:-config.example.json}"

"$PYTHON_BIN" scripts/build_writer.py --config "$CONFIG" --stage rules "$@"
