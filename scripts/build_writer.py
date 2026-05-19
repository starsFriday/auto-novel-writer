#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from auto_novel_writer.config import load_config
from auto_novel_writer.pipeline import run_stage


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build rules and write original Chinese novels from an opening.")
    parser.add_argument("--config", default="config.example.json", help="Config JSON path.")
    parser.add_argument("--run-mode", choices=["resume", "fresh"], default="", help="Override run.mode.")
    parser.add_argument(
        "--stage",
        choices=["index", "extract-rules", "synthesize", "rules", "plan", "extend-plan", "extend-outline", "write", "assemble", "all"],
        default="all",
        help="Pipeline stage.",
    )
    parser.add_argument("--opening", default="", help="Novel opening text.")
    parser.add_argument("--opening-file", default="", help="Path to a UTF-8 file containing the novel opening.")
    parser.add_argument("--project-id", default="", help="Stable output project id. Defaults to a hash of opening.")
    parser.add_argument("--limit-files", type=int, default=None, help="Limit corpus files for smoke tests.")
    parser.add_argument("--limit-rule-novels", type=int, default=None, help="Limit novels used for rule extraction.")
    parser.add_argument("--limit-rule-cards", type=int, default=None, help="Limit rule cards used for synthesis.")
    parser.add_argument("--start-chapter", type=int, default=1, help="First chapter number to write.")
    parser.add_argument("--chapter-count", type=int, default=None, help="Number of chapters to write.")
    parser.add_argument("--target-chapters", type=int, default=None, help="Override planning.target_chapters.")
    parser.add_argument("--target-chars", type=int, default=None, help="Override planning.target_chars_per_chapter.")
    parser.add_argument("--revision-rounds", type=int, default=None, help="Override generation.revision_rounds.")
    return parser.parse_args()


def read_opening(args: argparse.Namespace) -> str:
    if args.opening_file:
        return Path(args.opening_file).read_text(encoding="utf-8").strip()
    return args.opening.strip()


def main() -> int:
    args = parse_args()
    config = load_config(args.config)
    if args.run_mode:
        config["run"]["mode"] = args.run_mode
    if args.target_chapters is not None:
        config["planning"]["target_chapters"] = args.target_chapters
    if args.target_chars is not None:
        config["planning"]["target_chars_per_chapter"] = args.target_chars
    if args.revision_rounds is not None:
        config["generation"]["revision_rounds"] = args.revision_rounds
    result = run_stage(
        config,
        args.stage,
        opening=read_opening(args),
        project_id=args.project_id or None,
        limit_files=args.limit_files,
        limit_rule_novels=args.limit_rule_novels,
        limit_rule_cards=args.limit_rule_cards,
        start_chapter=args.start_chapter,
        chapter_count=args.chapter_count,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
