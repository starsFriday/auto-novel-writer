from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]


DEFAULT_CONFIG: dict[str, Any] = {
    "project": {
        "id": "auto-novel-writer-gpt55",
        "name": "Auto Novel Writer",
        "language": "zh-CN",
    },
    "run": {
        "mode": "resume",
    },
    "corpus": {
        "source_dirs": [
            "/root/tangfan/code/ComfyUI/novalv1",
            "/root/tangfan/code/ComfyUI/novalv2",
        ],
        "include_globs": ["*.txt"],
        "exclude_suffixes": [".crdownload"],
        "min_file_chars": 2000,
        "chunk_size": 4200,
        "max_samples_per_novel": 5,
        "max_files_per_source": 0,
        "sample_strategy": "spread",
    },
    "rule_extraction": {
        "max_novels": 120,
        "samples_per_novel": 5,
        "max_prompt_chars_per_novel": 14000,
        "batch_size_for_synthesis": 12,
        "final_rulebook_max_cards": 120,
    },
    "llm": {
        "provider": "codex-lb",
        "base_url": "https://codex-lb.vvicat.dev/v1",
        "api_key_env": "CODEX_LB_API_KEY",
        "model": "gpt-5.5",
        "judge_model": "gpt-5.5",
        "temperature": 0.7,
        "judge_temperature": 0.1,
        "max_tokens": 8192,
        "request_timeout": 300,
        "retries": 3,
        "retry_sleep_seconds": 2,
        "concurrency": 8,
        "extract_rules_concurrency": 8,
        "judge_concurrency": 4,
    },
    "planning": {
        "target_chapters": 12,
        "target_chars_per_chapter": 2600,
        "genre": "",
        "audience": "中文网文读者",
        "point_of_view": "第三人称有限视角",
        "tone": "强情节、人物有欲望、每章有推进",
        "must_include": [],
        "avoid": [
            "照搬语料中的角色名、地名、门派名、公司名或专有设定",
            "大段解释世界观但没有行动",
            "主角被动等待事件发生",
            "章节结尾没有新问题或新压力",
        ],
    },
    "generation": {
        "revision_rounds": 1,
        "run_checks_after_revision": True,
        "previous_chapter_tail_chars": 900,
        "previous_summary_count": 5,
        "system_prompt": "你是中文长篇小说创作工作流中的写作模型。必须写原创小说，抽取语料的抽象技法，但不能复刻任何已有作品的角色、句子、专有设定或剧情。",
    },
    "validation": {
        "min_logic_score": 4.0,
        "min_style_score": 4.0,
        "min_chapter_chars": 900,
        "max_repeated_ngrams": 10,
        "copy_check_ngram_chars": 34,
        "copy_check_max_samples": 200,
        "forbidden_phrases": [
            "作为AI",
            "作为一个AI",
            "作为大语言模型",
            "根据你提供的资料",
            "提示词",
            "我无法创作",
        ],
    },
    "paths": {
        "work_dir": "data",
        "manifest": "data/interim/corpus_manifest.jsonl",
        "samples": "data/interim/corpus_samples.jsonl",
        "rule_cards": "data/interim/rule_cards.jsonl",
        "partial_rulebooks": "data/interim/partial_rulebooks.jsonl",
        "rulebook": "data/final/novel_rulebook.json",
        "projects_dir": "data/projects",
    },
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    if not path:
        return copy.deepcopy(DEFAULT_CONFIG)
    config_path = Path(path)
    if not config_path.is_absolute():
        config_path = PROJECT_ROOT / config_path
    with config_path.open("r", encoding="utf-8") as handle:
        user_config = json.load(handle)
    return deep_merge(DEFAULT_CONFIG, user_config)


def resolve_project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def ensure_output_dirs(config: dict[str, Any]) -> None:
    for key, value in config["paths"].items():
        path = resolve_project_path(value)
        if key in {"work_dir", "projects_dir"}:
            path.mkdir(parents=True, exist_ok=True)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)


def get_run_mode(config: dict[str, Any]) -> str:
    mode = str(config.get("run", {}).get("mode", "resume")).strip().lower()
    if mode in {"resume", "continue", "incremental", "续跑", "继续生成"}:
        return "resume"
    if mode in {"fresh", "reset", "restart", "regenerate", "rebuild", "重新生成", "从头生成"}:
        return "fresh"
    raise ValueError(f"Unknown run.mode: {mode!r}; use 'resume' or 'fresh'")


def get_stage_concurrency(config: dict[str, Any], stage: str) -> int:
    llm_cfg = config.get("llm", {})
    stage_key = f"{stage}_concurrency"
    if stage_key in llm_cfg:
        return max(1, int(llm_cfg[stage_key]))
    if stage == "judge" and "judge_concurrency" in llm_cfg:
        return max(1, int(llm_cfg["judge_concurrency"]))
    return max(1, int(llm_cfg.get("concurrency", 1)))


def project_dir(config: dict[str, Any], project_id: str) -> Path:
    return resolve_project_path(config["paths"]["projects_dir"]) / project_id


def project_paths(config: dict[str, Any], project_id: str) -> dict[str, Path]:
    root = project_dir(config, project_id)
    return {
        "root": root,
        "brief": root / "brief.json",
        "plan": root / "novel_plan.json",
        "state": root / "writing_state.json",
        "chapters_dir": root / "chapters",
        "checks_dir": root / "checks",
        "novel_md": root / "novel.md",
        "report": root / "quality_report.json",
    }
