from __future__ import annotations

from pathlib import Path
from typing import Any

from . import chunking, io_utils
from .config import ensure_output_dirs, get_run_mode, resolve_project_path
from .json_utils import iter_jsonl, write_jsonl


def scan_files(source_dirs: list[str], include_globs: list[str], exclude_suffixes: list[str]) -> list[Path]:
    files: list[Path] = []
    for source in source_dirs:
        source_dir = Path(source)
        if not source_dir.exists():
            continue
        source_files: list[Path] = []
        for pattern in include_globs:
            source_files.extend(source_dir.rglob(pattern))
        normalized = []
        for path in sorted(set(source_files)):
            if not path.is_file():
                continue
            if any(str(path).endswith(suffix) for suffix in exclude_suffixes):
                continue
            normalized.append(path)
        files.extend(normalized)
    return files


def limit_files_by_source(files: list[Path], max_files_per_source: int) -> list[Path]:
    if max_files_per_source <= 0:
        return files
    counts: dict[str, int] = {}
    selected: list[Path] = []
    for path in files:
        source = path.parent.name
        if counts.get(source, 0) >= max_files_per_source:
            continue
        selected.append(path)
        counts[source] = counts.get(source, 0) + 1
    return selected


def build_manifest_and_samples(config: dict[str, Any], limit_files: int | None = None) -> dict[str, int]:
    ensure_output_dirs(config)
    manifest_path = resolve_project_path(config["paths"]["manifest"])
    samples_path = resolve_project_path(config["paths"]["samples"])
    if get_run_mode(config) == "resume" and limit_files is None and manifest_path.exists() and samples_path.exists():
        return {"files": sum(1 for _ in iter_jsonl(manifest_path)), "samples": sum(1 for _ in iter_jsonl(samples_path))}

    corpus_cfg = config["corpus"]
    files = scan_files(
        list(corpus_cfg["source_dirs"]),
        list(corpus_cfg["include_globs"]),
        list(corpus_cfg["exclude_suffixes"]),
    )
    files = limit_files_by_source(files, int(corpus_cfg.get("max_files_per_source", 0)))
    if limit_files:
        files = files[:limit_files]

    manifest_rows: list[dict[str, Any]] = []
    sample_rows: list[dict[str, Any]] = []
    for file_index, file_path in enumerate(files):
        raw_bytes = file_path.read_bytes()
        text, encoding = io_utils.read_text_file(file_path)
        text = io_utils.normalize_text(text)
        if len(text) < int(corpus_cfg["min_file_chars"]):
            continue
        title = chunking.novel_title_from_path(file_path)
        file_id = io_utils.stable_id(str(file_path), io_utils.sha1_bytes(raw_bytes))
        manifest_rows.append(
            {
                "file_id": file_id,
                "novel_title": title,
                "source_name": file_path.parent.name,
                "file_path": str(file_path),
                "encoding": encoding,
                "byte_size": len(raw_bytes),
                "char_count": len(text),
                "sha1": io_utils.sha1_bytes(raw_bytes),
                "file_index": file_index,
            }
        )
        sample_rows.extend(
            sample_novel_text(
                config=config,
                file_id=file_id,
                novel_title=title,
                file_path=str(file_path),
                text=text,
            )
        )

    write_jsonl(manifest_path, manifest_rows)
    write_jsonl(samples_path, sample_rows)
    return {"files": len(manifest_rows), "samples": len(sample_rows)}


def sample_novel_text(
    config: dict[str, Any],
    file_id: str,
    novel_title: str,
    file_path: str,
    text: str,
) -> list[dict[str, Any]]:
    corpus_cfg = config["corpus"]
    chunk_size = int(corpus_cfg["chunk_size"])
    max_samples = max(1, int(corpus_cfg["max_samples_per_novel"]))
    chapters = chunking.split_chapters(text)
    candidates: list[tuple[str, str, int]] = []

    candidates.append(("opening", text[:chunk_size], 0))
    if len(text) > chunk_size * 2:
        candidates.append(("ending", text[-chunk_size:], max(0, len(text) - chunk_size)))

    if chapters:
        spread_count = max(0, max_samples - len(candidates))
        indexes = spread_indexes(len(chapters), spread_count)
        for chapter_index in indexes:
            chapter_title, chapter_text = chapters[chapter_index]
            if not chapter_text.strip():
                continue
            kind = "chapter"
            if chapter_index == 0:
                kind = "first_chapter"
            elif chapter_index >= len(chapters) - 2:
                kind = "late_chapter"
            candidates.append((f"{kind}:{chapter_title[:40]}", chapter_text[:chunk_size], chapter_index))

    rows: list[dict[str, Any]] = []
    seen_content: set[str] = set()
    for sample_index, (sample_kind, content, chapter_index) in enumerate(candidates[:max_samples]):
        normalized = io_utils.normalize_text(content)
        if len(normalized) < 200:
            continue
        content_key = normalized[:160]
        if content_key in seen_content:
            continue
        seen_content.add(content_key)
        rows.append(
            {
                "sample_id": io_utils.stable_id(file_id, sample_kind, sample_index, normalized[:80]),
                "file_id": file_id,
                "novel_title": novel_title,
                "file_path": file_path,
                "sample_index": sample_index,
                "sample_kind": sample_kind,
                "chapter_index": chapter_index,
                "char_count": len(normalized),
                "dialogue_score": chunking.dialogue_score(normalized),
                "content": normalized,
            }
        )
    return rows


def spread_indexes(total: int, count: int) -> list[int]:
    if total <= 0 or count <= 0:
        return []
    if count >= total:
        return list(range(total))
    if count == 1:
        return [0]
    indexes = []
    for index in range(count):
        value = round(index * (total - 1) / (count - 1))
        if value not in indexes:
            indexes.append(value)
    return indexes


def samples_by_file(config: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for sample in iter_jsonl(resolve_project_path(config["paths"]["samples"])):
        grouped.setdefault(str(sample["file_id"]), []).append(sample)
    return grouped
