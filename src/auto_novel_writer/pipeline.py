from __future__ import annotations

import hashlib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Iterable

from .llm import make_llm_client
from .config import (
    PROJECT_ROOT,
    ensure_output_dirs,
    get_run_mode,
    get_stage_concurrency,
    project_paths,
    resolve_project_path,
)
from .corpus import build_manifest_and_samples, samples_by_file
from .json_utils import append_jsonl, iter_jsonl, read_json, write_json, write_jsonl
from .quality import deterministic_chapter_check


def log_status(message: str) -> None:
    print(message, file=sys.stderr, flush=True)


def stable_id(*parts: object, length: int = 16) -> str:
    joined = "\u241f".join(str(part) for part in parts)
    return hashlib.sha1(joined.encode("utf-8")).hexdigest()[:length]


def safe_project_id(opening: str, project_id: str | None = None) -> str:
    if project_id:
        cleaned = re.sub(r"[^0-9A-Za-z._-]+", "-", project_id.strip()).strip("-")
        if cleaned:
            return cleaned[:80]
    return "novel-" + stable_id(opening, length=12)


def format_duration(seconds: float) -> str:
    total_seconds = int(max(0, seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h{minutes:02d}m{seconds:02d}s"
    if minutes:
        return f"{minutes}m{seconds:02d}s"
    return f"{seconds}s"


class ProgressLogger:
    def __init__(self, label: str, total: int, concurrency: int | None = None) -> None:
        self.label = label
        self.total = max(0, total)
        self.completed = 0
        self.started_at = time.monotonic()
        self.last_logged_at = self.started_at
        self.step_size = 1 if self.total <= 100 else max(10, self.total // 100)
        self.next_log_count = min(self.step_size, self.total) if self.total else 0
        concurrency_text = f", concurrency={concurrency}" if concurrency is not None else ""
        log_status(f"[{self.label}] start total={self.total}{concurrency_text}")
        if self.total == 0:
            log_status(f"[{self.label}] done total=0 elapsed=0s")

    def advance(self) -> None:
        if self.total == 0:
            return
        self.completed += 1
        now = time.monotonic()
        should_log = (
            self.completed == self.total
            or self.completed <= min(3, self.total)
            or self.completed >= self.next_log_count
            or now - self.last_logged_at >= 30
        )
        if not should_log:
            return
        elapsed = now - self.started_at
        percent = (self.completed / self.total * 100) if self.total else 100.0
        rate_per_minute = self.completed / elapsed * 60 if elapsed > 0 else 0.0
        eta = (self.total - self.completed) / (rate_per_minute / 60) if rate_per_minute > 0 else 0
        log_status(
            f"[{self.label}] progress {self.completed}/{self.total} "
            f"({percent:.1f}%) elapsed={format_duration(elapsed)} "
            f"rate={rate_per_minute:.1f}/min eta={format_duration(eta)}"
        )
        self.last_logged_at = now
        while self.next_log_count <= self.completed and self.next_log_count < self.total:
            self.next_log_count += self.step_size


def load_prompt(name: str) -> str:
    return (PROJECT_ROOT / "prompts" / name).read_text(encoding="utf-8")


def render_template(template: str, values: dict[str, Any]) -> str:
    rendered = template
    for key, value in values.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
    return rendered


def remove_output(path: Path) -> None:
    if path.exists():
        path.unlink()
        log_status(f"[run] removed {path}")


def reset_outputs_for_stage(config: dict[str, Any], stage: str) -> None:
    paths = config["paths"]
    downstream_keys = {
        "index": ["manifest", "samples", "rule_cards", "partial_rulebooks", "rulebook"],
        "extract_rules": ["rule_cards", "partial_rulebooks", "rulebook"],
        "synthesize": ["partial_rulebooks", "rulebook"],
    }
    for key in downstream_keys.get(stage, []):
        remove_output(resolve_project_path(paths[key]))


def select_spread(rows: list[Any], limit: int | None) -> list[Any]:
    if not limit or limit <= 0 or len(rows) <= limit:
        return rows
    selected = []
    for index in range(limit):
        selected.append(rows[int(index * len(rows) / limit)])
    return selected


def extract_rule_cards(config: dict[str, Any], limit_novels: int | None = None) -> dict[str, int]:
    ensure_output_dirs(config)
    if get_run_mode(config) == "fresh":
        reset_outputs_for_stage(config, "extract_rules")

    manifest = list(iter_jsonl(resolve_project_path(config["paths"]["manifest"])))
    grouped_samples = samples_by_file(config)
    max_novels = limit_novels or int(config["rule_extraction"].get("max_novels", 0))
    selected_manifest = select_manifest_balanced(manifest, max_novels)

    output_path = resolve_project_path(config["paths"]["rule_cards"])
    existing = {str(row.get("file_id")): row for row in iter_jsonl(output_path)}
    jobs = [row for row in selected_manifest if row.get("file_id") not in existing and grouped_samples.get(str(row["file_id"]))]
    if existing:
        log_status(f"[extract-rules] resume existing={len(existing)} pending={len(jobs)} total={len(selected_manifest)}")

    client = make_llm_client(config)
    prompt_template = load_prompt("extract_rules_zh.md")

    def process(row: dict[str, Any]) -> dict[str, Any]:
        file_id = str(row["file_id"])
        samples = grouped_samples[file_id][: int(config["rule_extraction"].get("samples_per_novel", 5))]
        prompt = render_template(
            prompt_template,
            {
                "novel_title": row.get("novel_title", ""),
                "source_name": row.get("source_name", ""),
                "samples": format_samples_for_prompt(samples, int(config["rule_extraction"]["max_prompt_chars_per_novel"])),
            },
        )
        result = client.complete_json(
            [
                {"role": "system", "content": "你是严格的中文小说写作规则抽取器，只输出 JSON。"},
                {"role": "user", "content": prompt},
            ]
        )
        if not isinstance(result, dict):
            raise ValueError("rule extraction output is not JSON object")
        card = normalize_rule_card(result)
        card.update(
            {
                "rule_card_id": stable_id(file_id, row.get("sha1", "")),
                "file_id": file_id,
                "novel_title": row.get("novel_title", ""),
                "source_name": row.get("source_name", ""),
                "model": config["llm"]["model"],
            }
        )
        return card

    concurrency = get_stage_concurrency(config, "extract_rules")
    progress = ProgressLogger("extract-rules", len(jobs), concurrency=concurrency)
    failed_path = output_path.with_name(f"{output_path.stem}.failed.jsonl")
    failed = 0
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(process, row): row for row in jobs}
        for future in as_completed(futures):
            row = futures[future]
            try:
                card = future.result()
            except Exception as exc:
                failed += 1
                append_jsonl(
                    failed_path,
                    {
                        "file_id": row.get("file_id", ""),
                        "novel_title": row.get("novel_title", ""),
                        "error": str(exc),
                        "failed_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    },
                )
                log_status(f"[extract-rules] failed novel={row.get('novel_title', '')}: {exc}")
            else:
                existing[str(card["file_id"])] = card
                append_jsonl(output_path, card)
            progress.advance()

    ordered = [existing[str(row["file_id"])] for row in selected_manifest if str(row["file_id"]) in existing]
    write_jsonl(output_path, ordered)
    return {"rule_cards": len(ordered), "failed_rule_cards": failed}


def select_manifest_balanced(manifest: list[dict[str, Any]], limit: int | None) -> list[dict[str, Any]]:
    if not limit or limit <= 0 or len(manifest) <= limit:
        return manifest
    by_source: dict[str, list[dict[str, Any]]] = {}
    for row in manifest:
        by_source.setdefault(str(row.get("source_name", "")), []).append(row)
    sources = sorted(by_source)
    per_source = max(1, limit // max(1, len(sources)))
    selected: list[dict[str, Any]] = []
    for source in sources:
        selected.extend(select_spread(by_source[source], per_source))
    if len(selected) < limit:
        selected_ids = {row["file_id"] for row in selected}
        remainder = [row for row in manifest if row["file_id"] not in selected_ids]
        selected.extend(select_spread(remainder, limit - len(selected)))
    return selected[:limit]


def format_samples_for_prompt(samples: list[dict[str, Any]], max_chars: int) -> str:
    if not samples:
        return ""
    per_sample = max(800, max_chars // len(samples))
    blocks = []
    used = 0
    for index, sample in enumerate(samples, start=1):
        remaining = max_chars - used
        if remaining <= 0:
            break
        content = str(sample.get("content", ""))[: min(per_sample, remaining)]
        used += len(content)
        blocks.append(
            "\n".join(
                [
                    f"### 样本 {index}",
                    f"- 类型: {sample.get('sample_kind', '')}",
                    f"- 对话密度: {sample.get('dialogue_score', 0)}",
                    "",
                    content,
                ]
            )
        )
    return "\n\n".join(blocks)


def normalize_rule_card(card: dict[str, Any]) -> dict[str, Any]:
    fields = {
        "genre_guess": "",
        "reader_promise": [],
        "opening_hook_rules": [],
        "worldbuilding_rules": [],
        "outline_rules": [],
        "character_rules": [],
        "chapter_design_rules": [],
        "conflict_design_rules": [],
        "dialogue_rules": [],
        "pacing_rules": [],
        "prose_style_rules": [],
        "revision_rules": [],
        "logic_risks": [],
        "avoid_rules": [],
    }
    normalized: dict[str, Any] = {}
    for key, default in fields.items():
        value = card.get(key, default)
        if isinstance(default, list) and not isinstance(value, list):
            value = [str(value)] if str(value).strip() else []
        normalized[key] = value
    return normalized


def synthesize_rulebook(config: dict[str, Any], limit_cards: int | None = None) -> dict[str, int]:
    ensure_output_dirs(config)
    if get_run_mode(config) == "fresh":
        reset_outputs_for_stage(config, "synthesize")

    rulebook_path = resolve_project_path(config["paths"]["rulebook"])
    if get_run_mode(config) == "resume" and limit_cards is None and rulebook_path.exists():
        return {"rulebooks": 1, "partial_rulebooks": sum(1 for _ in iter_jsonl(resolve_project_path(config["paths"]["partial_rulebooks"])))}

    cards = list(iter_jsonl(resolve_project_path(config["paths"]["rule_cards"])))
    if limit_cards:
        cards = cards[:limit_cards]
    max_cards = int(config["rule_extraction"].get("final_rulebook_max_cards", 0))
    cards = select_spread(cards, max_cards)
    if not cards:
        raise ValueError("No rule cards found. Run --stage extract-rules first.")

    client = make_llm_client(config)
    batch_size = max(1, int(config["rule_extraction"].get("batch_size_for_synthesis", 12)))
    prompt_template = load_prompt("synthesize_rules_zh.md")
    batches = [cards[index : index + batch_size] for index in range(0, len(cards), batch_size)]
    partials: list[dict[str, Any]] = []
    partial_path = resolve_project_path(config["paths"]["partial_rulebooks"])

    progress = ProgressLogger("synthesize-rules", len(batches), concurrency=1)
    for batch_index, batch in enumerate(batches):
        result = client.complete_json(
            [
                {"role": "system", "content": "你是中文商业小说方法论编辑，只输出 JSON。"},
                {
                    "role": "user",
                    "content": render_template(
                        prompt_template,
                        {
                            "mode": "partial",
                            "cards": json.dumps([compact_rule_card(card) for card in batch], ensure_ascii=False, indent=2),
                        },
                    ),
                },
            ]
        )
        if not isinstance(result, dict):
            raise ValueError("partial rulebook output is not JSON object")
        result["partial_index"] = batch_index
        result["source_rule_cards"] = len(batch)
        partials.append(result)
        append_jsonl(partial_path, result)
        progress.advance()

    final_input = partials if len(partials) > 1 else partials[0].get("rules", partials[0])
    final = client.complete_json(
        [
            {"role": "system", "content": "你是中文长篇小说总编，只输出 JSON。"},
            {
                "role": "user",
                "content": render_template(
                    prompt_template,
                    {
                        "mode": "final",
                        "cards": json.dumps(final_input, ensure_ascii=False, indent=2),
                    },
                ),
            },
        ]
    )
    if not isinstance(final, dict):
        raise ValueError("final rulebook output is not JSON object")
    final.setdefault("meta", {})
    final["meta"].update(
        {
            "source_rule_cards": len(cards),
            "partial_rulebooks": len(partials),
            "model": config["llm"]["model"],
            "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "anti_copy_notice": "只保留抽象写作规则，不复刻语料中的句子、角色、专有名词或剧情。",
        }
    )
    write_json(rulebook_path, final)
    return {"rulebooks": 1, "partial_rulebooks": len(partials), "source_rule_cards": len(cards)}


def compact_rule_card(card: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "novel_title",
        "source_name",
        "genre_guess",
        "reader_promise",
        "opening_hook_rules",
        "worldbuilding_rules",
        "outline_rules",
        "character_rules",
        "chapter_design_rules",
        "conflict_design_rules",
        "dialogue_rules",
        "pacing_rules",
        "prose_style_rules",
        "revision_rules",
        "logic_risks",
        "avoid_rules",
    ]
    return {key: card.get(key) for key in keys if key in card}


def plan_novel(config: dict[str, Any], opening: str, project_id: str | None = None) -> dict[str, Any]:
    ensure_output_dirs(config)
    if not opening.strip():
        raise ValueError("Opening text is required for planning.")
    rulebook = read_json(resolve_project_path(config["paths"]["rulebook"]))
    if not rulebook:
        raise ValueError("Rulebook not found. Run --stage synthesize first.")

    final_project_id = safe_project_id(opening, project_id)
    paths = project_paths(config, final_project_id)
    paths["root"].mkdir(parents=True, exist_ok=True)
    paths["chapters_dir"].mkdir(parents=True, exist_ok=True)
    paths["checks_dir"].mkdir(parents=True, exist_ok=True)

    brief = {
        "project_id": final_project_id,
        "opening": opening.strip(),
        "planning": config["planning"],
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    write_json(paths["brief"], brief)

    prompt = render_template(
        load_prompt("plan_novel_zh.md"),
        {
            "opening": opening.strip(),
            "planning": json.dumps(config["planning"], ensure_ascii=False, indent=2),
            "rulebook": json.dumps(rulebook, ensure_ascii=False, indent=2)[:28000],
        },
    )
    client = make_llm_client(config)
    result = client.complete_json(
        [
            {"role": "system", "content": config["generation"]["system_prompt"]},
            {"role": "user", "content": prompt},
        ]
    )
    if not isinstance(result, dict):
        raise ValueError("novel plan output is not JSON object")
    plan = normalize_plan(result, config)
    plan["project_id"] = final_project_id
    plan["opening"] = opening.strip()
    write_json(paths["plan"], plan)
    write_json(
        paths["state"],
        {
            "project_id": final_project_id,
            "summaries": [],
            "continuity": plan.get("continuity_bible", {}),
            "open_threads": [],
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        },
    )
    return {"project_id": final_project_id, "plan": plan, "plan_path": str(paths["plan"])}


def normalize_plan(plan: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    target_chapters = int(config["planning"]["target_chapters"])
    plan.setdefault("title", "未命名长篇")
    plan.setdefault("genre", config["planning"].get("genre", "") or "原创中文长篇")
    plan.setdefault("logline", "")
    plan.setdefault("theme", "")
    plan.setdefault("worldview", {})
    plan.setdefault("characters", [])
    plan.setdefault("conflict_design", {})
    plan.setdefault("continuity_bible", {})
    plan.setdefault("style_guide", {})
    chapter_plan = plan.get("chapter_plan")
    if not isinstance(chapter_plan, list):
        chapter_plan = []
    for chapter_no in range(1, target_chapters + 1):
        if len(chapter_plan) >= chapter_no and isinstance(chapter_plan[chapter_no - 1], dict):
            chapter_plan[chapter_no - 1].setdefault("chapter_no", chapter_no)
            continue
        chapter_plan.append(
            {
                "chapter_no": chapter_no,
                "title": f"第{chapter_no}章",
                "goal": "推进主线并制造新的压力",
                "conflict": "人物欲望和外部阻力正面相撞",
                "turning_point": "章节末出现改变局面的信息或行动",
                "cliffhanger": "留下下一章必须解决的问题",
            }
        )
    plan["chapter_plan"] = chapter_plan[:target_chapters]
    return plan


def write_novel(
    config: dict[str, Any],
    project_id: str,
    start_chapter: int = 1,
    chapter_count: int | None = None,
) -> dict[str, Any]:
    paths = project_paths(config, project_id)
    plan = read_json(paths["plan"])
    if not plan:
        raise ValueError(f"Plan not found for project_id={project_id}: {paths['plan']}")
    rulebook = read_json(resolve_project_path(config["paths"]["rulebook"]))
    if not rulebook:
        raise ValueError("Rulebook not found. Run --stage synthesize first.")

    paths["chapters_dir"].mkdir(parents=True, exist_ok=True)
    paths["checks_dir"].mkdir(parents=True, exist_ok=True)
    chapter_plan = list(plan.get("chapter_plan", []))
    target_chapters = len(chapter_plan) or int(config["planning"]["target_chapters"])
    end_chapter = target_chapters if chapter_count is None else min(target_chapters, start_chapter + chapter_count - 1)
    chapter_numbers = list(range(max(1, start_chapter), end_chapter + 1))

    client = make_llm_client(config)
    judge_client = make_llm_client(config, judge=True)
    source_samples = load_copy_check_samples(config)
    progress = ProgressLogger("write", len(chapter_numbers), concurrency=1)
    written = []
    for chapter_no in chapter_numbers:
        item = write_one_chapter(config, project_id, plan, rulebook, chapter_no, client, judge_client, source_samples)
        written.append(item)
        progress.advance()

    assemble_novel(config, project_id)
    report = write_quality_report(config, project_id)
    return {"project_id": project_id, "chapters_written": len(written), "novel_path": str(paths["novel_md"]), "report": report}


def chapter_json_path(config: dict[str, Any], project_id: str, chapter_no: int) -> Path:
    return project_paths(config, project_id)["chapters_dir"] / f"chapter_{chapter_no:03d}.json"


def chapter_md_path(config: dict[str, Any], project_id: str, chapter_no: int) -> Path:
    return project_paths(config, project_id)["chapters_dir"] / f"chapter_{chapter_no:03d}.md"


def write_one_chapter(
    config: dict[str, Any],
    project_id: str,
    plan: dict[str, Any],
    rulebook: dict[str, Any],
    chapter_no: int,
    client: Any,
    judge_client: Any,
    source_samples: list[dict[str, Any]],
) -> dict[str, Any]:
    json_path = chapter_json_path(config, project_id, chapter_no)
    md_path = chapter_md_path(config, project_id, chapter_no)
    if get_run_mode(config) == "resume" and json_path.exists():
        return read_json(json_path)

    state = read_json(project_paths(config, project_id)["state"], default={}) or {}
    chapter_plan = get_chapter_plan(plan, chapter_no)
    previous_context = build_previous_context(config, project_id, state, chapter_no)
    prompt = render_template(
        load_prompt("write_chapter_zh.md"),
        {
            "chapter_no": chapter_no,
            "target_chars": config["planning"]["target_chars_per_chapter"],
            "opening": plan.get("opening", ""),
            "plan": json.dumps(plan, ensure_ascii=False, indent=2)[:22000],
            "rulebook": json.dumps(rulebook, ensure_ascii=False, indent=2)[:18000],
            "chapter_plan": json.dumps(chapter_plan, ensure_ascii=False, indent=2),
            "previous_context": previous_context,
        },
    )
    result = client.complete_json(
        [
            {"role": "system", "content": config["generation"]["system_prompt"]},
            {"role": "user", "content": prompt},
        ]
    )
    if not isinstance(result, dict):
        raise ValueError("chapter output is not JSON object")

    draft = str(result.get("draft", "")).strip()
    if not draft:
        raise ValueError(f"chapter {chapter_no} draft is empty")

    checks = run_chapter_checks(config, plan, chapter_plan, draft, judge_client, source_samples)
    revisions = []
    final_draft = draft
    revision_rounds = int(config["generation"].get("revision_rounds", 0))
    for round_index in range(revision_rounds):
        if not needs_revision(config, checks):
            break
        revision = revise_chapter(config, plan, chapter_plan, final_draft, checks, client)
        if not revision.get("revised_draft"):
            break
        revisions.append(revision)
        final_draft = str(revision["revised_draft"]).strip()
        if bool(config["generation"].get("run_checks_after_revision", True)):
            checks = run_chapter_checks(config, plan, chapter_plan, final_draft, judge_client, source_samples)
        else:
            checks["deterministic"] = deterministic_chapter_check(final_draft, config, source_samples)

    title = str(result.get("title") or chapter_plan.get("title") or f"第{chapter_no}章").strip()
    chapter_item = {
        "project_id": project_id,
        "chapter_no": chapter_no,
        "title": title,
        "chapter_plan": chapter_plan,
        "draft": draft,
        "final_draft": final_draft,
        "chapter_summary": str(result.get("chapter_summary", "")).strip(),
        "continuity_updates": result.get("continuity_updates", []),
        "open_threads": result.get("open_threads", []),
        "checks": checks,
        "revisions": revisions,
        "model": config["llm"]["model"],
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    write_json(json_path, chapter_item)
    md_path.write_text(f"# {title}\n\n{final_draft}\n", encoding="utf-8")
    update_state(config, project_id, chapter_item)
    return chapter_item


def get_chapter_plan(plan: dict[str, Any], chapter_no: int) -> dict[str, Any]:
    for item in plan.get("chapter_plan", []):
        if int(item.get("chapter_no", 0)) == chapter_no:
            return item
    return {"chapter_no": chapter_no, "title": f"第{chapter_no}章"}


def build_previous_context(config: dict[str, Any], project_id: str, state: dict[str, Any], chapter_no: int) -> str:
    previous_summary_count = int(config["generation"].get("previous_summary_count", 5))
    summaries = state.get("summaries", [])[-previous_summary_count:]
    previous_tail = ""
    if chapter_no > 1:
        previous = read_json(chapter_json_path(config, project_id, chapter_no - 1), default={}) or {}
        previous_tail = str(previous.get("final_draft", ""))[-int(config["generation"].get("previous_chapter_tail_chars", 900)) :]
    return json.dumps(
        {
            "recent_summaries": summaries,
            "continuity": state.get("continuity", {}),
            "open_threads": state.get("open_threads", []),
            "previous_chapter_tail": previous_tail,
        },
        ensure_ascii=False,
        indent=2,
    )


def run_chapter_checks(
    config: dict[str, Any],
    plan: dict[str, Any],
    chapter_plan: dict[str, Any],
    draft: str,
    judge_client: Any,
    source_samples: list[dict[str, Any]],
) -> dict[str, Any]:
    deterministic = deterministic_chapter_check(draft, config, source_samples)
    logic = run_json_judge(
        config,
        judge_client,
        "logic_check_zh.md",
        {
            "plan": json.dumps(plan, ensure_ascii=False, indent=2)[:20000],
            "chapter_plan": json.dumps(chapter_plan, ensure_ascii=False, indent=2),
            "draft": draft,
        },
    )
    style = run_json_judge(
        config,
        judge_client,
        "style_eval_zh.md",
        {
            "rulebook": json.dumps(read_json(resolve_project_path(config["paths"]["rulebook"]), default={}), ensure_ascii=False, indent=2)[:16000],
            "chapter_plan": json.dumps(chapter_plan, ensure_ascii=False, indent=2),
            "draft": draft,
        },
    )
    return {"deterministic": deterministic, "logic": logic, "style": style}


def run_json_judge(config: dict[str, Any], client: Any, prompt_name: str, values: dict[str, Any]) -> dict[str, Any]:
    try:
        result = client.complete_json(
            [
                {"role": "system", "content": "你是严格的中文小说质量编辑，只输出 JSON。"},
                {"role": "user", "content": render_template(load_prompt(prompt_name), values)},
            ],
            temperature=config["llm"].get("judge_temperature", 0.1),
        )
    except Exception as exc:
        return {"score": 0.0, "confirmed": False, "issues": [f"judge failed: {exc}"], "error": str(exc)}
    if not isinstance(result, dict):
        return {"score": 0.0, "confirmed": False, "issues": ["judge output is not JSON object"]}
    result.setdefault("score", 0.0)
    result.setdefault("confirmed", False)
    result.setdefault("issues", [])
    return result


def needs_revision(config: dict[str, Any], checks: dict[str, Any]) -> bool:
    deterministic = checks.get("deterministic", {})
    if deterministic.get("issues"):
        return True
    logic = checks.get("logic", {})
    if not logic.get("error") and float(logic.get("score", 0.0)) < float(config["validation"]["min_logic_score"]):
        return True
    style = checks.get("style", {})
    if not style.get("error") and float(style.get("score", 0.0)) < float(config["validation"]["min_style_score"]):
        return True
    return False


def revise_chapter(
    config: dict[str, Any],
    plan: dict[str, Any],
    chapter_plan: dict[str, Any],
    draft: str,
    checks: dict[str, Any],
    client: Any,
) -> dict[str, Any]:
    result = client.complete_json(
        [
            {"role": "system", "content": config["generation"]["system_prompt"]},
            {
                "role": "user",
                "content": render_template(
                    load_prompt("revise_chapter_zh.md"),
                    {
                        "plan": json.dumps(plan, ensure_ascii=False, indent=2)[:18000],
                        "chapter_plan": json.dumps(chapter_plan, ensure_ascii=False, indent=2),
                        "checks": json.dumps(checks, ensure_ascii=False, indent=2),
                        "draft": draft,
                    },
                ),
            },
        ]
    )
    if not isinstance(result, dict):
        return {"revised_draft": "", "revision_notes": ["revision output is not JSON object"]}
    result.setdefault("revised_draft", "")
    result.setdefault("revision_notes", [])
    return result


def update_state(config: dict[str, Any], project_id: str, chapter: dict[str, Any]) -> None:
    paths = project_paths(config, project_id)
    state = read_json(paths["state"], default={}) or {}
    summaries = [item for item in state.get("summaries", []) if int(item.get("chapter_no", 0)) != int(chapter["chapter_no"])]
    summaries.append(
        {
            "chapter_no": chapter["chapter_no"],
            "title": chapter["title"],
            "summary": chapter.get("chapter_summary", ""),
            "open_threads": chapter.get("open_threads", []),
            "continuity_updates": chapter.get("continuity_updates", []),
        }
    )
    summaries = sorted(summaries, key=lambda item: int(item.get("chapter_no", 0)))
    open_threads = []
    for item in summaries:
        for thread in item.get("open_threads", []):
            if thread not in open_threads:
                open_threads.append(thread)
    state.update(
        {
            "project_id": project_id,
            "summaries": summaries,
            "open_threads": open_threads[-30:],
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
    )
    write_json(paths["state"], state)


def load_copy_check_samples(config: dict[str, Any]) -> list[dict[str, Any]]:
    samples = list(iter_jsonl(resolve_project_path(config["paths"]["samples"])))
    return select_spread(samples, int(config["validation"].get("copy_check_max_samples", 200)))


def assemble_novel(config: dict[str, Any], project_id: str) -> None:
    paths = project_paths(config, project_id)
    plan = read_json(paths["plan"], default={}) or {}
    chapters = []
    for path in sorted(paths["chapters_dir"].glob("chapter_*.json")):
        item = read_json(path)
        if item:
            chapters.append(item)
    lines = [f"# {plan.get('title', '未命名长篇')}", ""]
    if plan.get("logline"):
        lines.extend([f"> {plan['logline']}", ""])
    for chapter in sorted(chapters, key=lambda item: int(item.get("chapter_no", 0))):
        lines.extend([f"## {chapter.get('title', '')}", "", str(chapter.get("final_draft", "")).strip(), ""])
    paths["novel_md"].write_text("\n".join(lines).strip() + "\n", encoding="utf-8")


def write_quality_report(config: dict[str, Any], project_id: str) -> dict[str, Any]:
    paths = project_paths(config, project_id)
    chapters = [read_json(path) for path in sorted(paths["chapters_dir"].glob("chapter_*.json"))]
    chapters = [item for item in chapters if item]
    rows = []
    for chapter in chapters:
        checks = chapter.get("checks", {})
        rows.append(
            {
                "chapter_no": chapter.get("chapter_no"),
                "title": chapter.get("title"),
                "deterministic_score": checks.get("deterministic", {}).get("score", 0),
                "logic_score": checks.get("logic", {}).get("score", 0),
                "style_score": checks.get("style", {}).get("score", 0),
                "issues": list(checks.get("deterministic", {}).get("issues", []))
                + list(checks.get("logic", {}).get("issues", []))
                + list(checks.get("style", {}).get("issues", [])),
            }
        )
    report = {
        "project_id": project_id,
        "chapters": rows,
        "chapter_count": len(rows),
        "avg_logic_score": average([float(row["logic_score"]) for row in rows]),
        "avg_style_score": average([float(row["style_score"]) for row in rows]),
        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
    }
    write_json(paths["report"], report)
    return report


def average(values: Iterable[float]) -> float:
    values = list(values)
    return round(sum(values) / len(values), 3) if values else 0.0


def run_stage(
    config: dict[str, Any],
    stage: str,
    opening: str | None = None,
    project_id: str | None = None,
    limit_files: int | None = None,
    limit_rule_novels: int | None = None,
    limit_rule_cards: int | None = None,
    start_chapter: int = 1,
    chapter_count: int | None = None,
) -> dict[str, Any]:
    normalized_stage = stage.replace("_", "-")
    if normalized_stage == "index":
        if get_run_mode(config) == "fresh":
            reset_outputs_for_stage(config, "index")
        return build_manifest_and_samples(config, limit_files=limit_files)
    if normalized_stage == "extract-rules":
        return extract_rule_cards(config, limit_novels=limit_rule_novels)
    if normalized_stage in {"synthesize", "synthesize-rules"}:
        return synthesize_rulebook(config, limit_cards=limit_rule_cards)
    if normalized_stage == "rules":
        result: dict[str, Any] = {}
        if get_run_mode(config) == "fresh":
            reset_outputs_for_stage(config, "index")
        result.update(build_manifest_and_samples(config, limit_files=limit_files))
        result.update(extract_rule_cards(config, limit_novels=limit_rule_novels))
        result.update(synthesize_rulebook(config, limit_cards=limit_rule_cards))
        return result
    if normalized_stage == "plan":
        if opening is None:
            raise ValueError("--opening or --opening-file is required for --stage plan")
        planned = plan_novel(config, opening, project_id=project_id)
        return {"project_id": planned["project_id"], "plan_path": planned["plan_path"]}
    if normalized_stage == "write":
        if not project_id:
            if opening:
                project_id = safe_project_id(opening)
            else:
                raise ValueError("--project-id is required for --stage write")
        return write_novel(config, project_id, start_chapter=start_chapter, chapter_count=chapter_count)
    if normalized_stage == "assemble":
        if not project_id:
            raise ValueError("--project-id is required for --stage assemble")
        assemble_novel(config, project_id)
        return {"project_id": project_id, "novel_path": str(project_paths(config, project_id)["novel_md"])}
    if normalized_stage == "all":
        if opening is None:
            raise ValueError("--opening or --opening-file is required for --stage all")
        result: dict[str, Any] = {}
        if get_run_mode(config) == "fresh":
            reset_outputs_for_stage(config, "index")
        result.update(build_manifest_and_samples(config, limit_files=limit_files))
        result.update(extract_rule_cards(config, limit_novels=limit_rule_novels))
        result.update(synthesize_rulebook(config, limit_cards=limit_rule_cards))
        planned = plan_novel(config, opening, project_id=project_id)
        result["project_id"] = planned["project_id"]
        result.update(write_novel(config, planned["project_id"], start_chapter=start_chapter, chapter_count=chapter_count))
        return result
    raise ValueError(f"Unknown stage: {stage}")
