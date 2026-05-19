from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from .io_utils import stable_id


CHAPTER_RE = re.compile(
    r"^\s*((?:第[一二三四五六七八九十百千万两零〇\d]+[章节回卷集部][^\n]{0,50})|"
    r"(?:正文[^\n]{0,50})|(?:楔子)|(?:序章)|(?:尾声))\s*$",
    re.MULTILINE,
)


def novel_title_from_path(path: str | Path) -> str:
    name = Path(path).name
    if name.endswith(".txt"):
        name = name[:-4]
    return name


def split_chapters(text: str) -> list[tuple[str, str]]:
    matches = list(CHAPTER_RE.finditer(text))
    if not matches:
        return [("全文", text)]

    chapters: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        title = match.group(1).strip()
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if body:
            chapters.append((title, body))

    if matches[0].start() > 0:
        preface = text[: matches[0].start()].strip()
        if preface:
            chapters.insert(0, ("卷首", preface))
    return chapters or [("全文", text)]


def dialogue_score(text: str) -> int:
    quote_marks = sum(text.count(mark) for mark in ("“", "”", "‘", "’", "「", "」", "『", "』"))
    colon_lines = len(re.findall(r"^[^，。！？\n]{1,12}[：:]", text, flags=re.MULTILINE))
    speech_verbs = len(re.findall(r"(说道|问道|笑道|冷笑|叹道|喝道|叫道|回答|低声|沉声)", text))
    return quote_marks + colon_lines * 2 + speech_verbs


def sliding_chunks(chapter_title: str, text: str, chunk_size: int, overlap: int) -> list[tuple[str, str]]:
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n{2,}", text) if paragraph.strip()]
    chunks: list[tuple[str, str]] = []
    buffer: list[str] = []
    size = 0

    def flush() -> None:
        nonlocal buffer, size
        if not buffer:
            return
        chunk_text = "\n\n".join(buffer).strip()
        if chunk_text:
            chunks.append((chapter_title, chunk_text))
        if overlap > 0 and chunk_text:
            tail = chunk_text[-overlap:]
            buffer = [tail]
            size = len(tail)
        else:
            buffer = []
            size = 0

    for paragraph in paragraphs:
        if len(paragraph) > chunk_size:
            flush()
            start = 0
            step = max(1, chunk_size - overlap)
            while start < len(paragraph):
                part = paragraph[start : start + chunk_size].strip()
                if part:
                    chunks.append((chapter_title, part))
                start += step
            buffer = []
            size = 0
            continue
        if size + len(paragraph) + 2 > chunk_size:
            flush()
        buffer.append(paragraph)
        size += len(paragraph) + 2
    flush()
    return chunks


def select_chunks(chunks: list[dict[str, Any]], max_chunks: int, dialogue_bias: bool) -> list[dict[str, Any]]:
    if max_chunks <= 0 or len(chunks) <= max_chunks:
        return chunks
    if not dialogue_bias:
        step = len(chunks) / max_chunks
        return [chunks[int(index * step)] for index in range(max_chunks)]

    top_count = max(1, int(max_chunks * 0.7))
    spread_count = max_chunks - top_count
    top = sorted(chunks, key=lambda item: item["dialogue_score"], reverse=True)[:top_count]
    seen = {item["chunk_id"] for item in top}
    spread: list[dict[str, Any]] = []
    if spread_count > 0:
        step = len(chunks) / spread_count
        for index in range(spread_count):
            candidate = chunks[min(len(chunks) - 1, int(index * step))]
            if candidate["chunk_id"] not in seen:
                spread.append(candidate)
                seen.add(candidate["chunk_id"])
    selected = top + spread
    return sorted(selected[:max_chunks], key=lambda item: item["chunk_index"])


def build_chunks_for_text(
    novel_title: str,
    file_path: str,
    text: str,
    chunk_size: int,
    overlap: int,
    max_chunks: int,
    dialogue_bias: bool,
) -> list[dict[str, Any]]:
    chunks: list[dict[str, Any]] = []
    chunk_index = 0
    for chapter_index, (chapter_title, chapter_text) in enumerate(split_chapters(text)):
        for title, content in sliding_chunks(chapter_title, chapter_text, chunk_size, overlap):
            chunk_id = stable_id(novel_title, file_path, chapter_index, chunk_index, content[:80])
            chunks.append(
                {
                    "chunk_id": chunk_id,
                    "novel_title": novel_title,
                    "file_path": file_path,
                    "chapter_index": chapter_index,
                    "chapter_title": title,
                    "chunk_index": chunk_index,
                    "content": content,
                    "char_count": len(content),
                    "dialogue_score": dialogue_score(content),
                }
            )
            chunk_index += 1
    return select_chunks(chunks, max_chunks, dialogue_bias)

