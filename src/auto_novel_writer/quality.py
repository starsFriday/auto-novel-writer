from __future__ import annotations

import re
from collections import Counter
from typing import Any


def normalize_for_overlap(text: str) -> str:
    return re.sub(r"\s+", "", text)


def visible_length(text: str) -> int:
    return len(normalize_for_overlap(text))


def repeated_ngram_count(text: str, n: int = 10) -> int:
    chars = normalize_for_overlap(text)
    if len(chars) < n:
        return 0
    counts = Counter(chars[index : index + n] for index in range(len(chars) - n + 1))
    return max(counts.values(), default=0)


def copy_risk_hits(draft: str, source_samples: list[dict[str, Any]], n: int = 34, max_hits: int = 5) -> list[str]:
    draft_text = normalize_for_overlap(draft)
    if len(draft_text) < n:
        return []
    draft_ngrams = {draft_text[index : index + n] for index in range(len(draft_text) - n + 1)}
    hits: list[str] = []
    for sample in source_samples:
        source_text = normalize_for_overlap(str(sample.get("content", "")))
        if len(source_text) < n:
            continue
        for index in range(len(source_text) - n + 1):
            phrase = source_text[index : index + n]
            if phrase in draft_ngrams:
                hits.append(phrase)
                break
        if len(hits) >= max_hits:
            break
    return hits


def deterministic_chapter_check(
    draft: str,
    config: dict[str, Any],
    source_samples: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    validation = config["validation"]
    issues: list[str] = []
    forbidden = [str(item) for item in validation.get("forbidden_phrases", [])]
    for phrase in forbidden:
        if phrase and phrase in draft:
            issues.append(f"出现禁用短语: {phrase}")

    length = visible_length(draft)
    min_chars = int(validation.get("min_chapter_chars", 0))
    if length < min_chars:
        issues.append(f"章节过短: {length} < {min_chars}")

    max_repeated = int(validation.get("max_repeated_ngrams", 10))
    repeated = repeated_ngram_count(draft, n=10)
    if repeated > max_repeated:
        issues.append(f"重复片段过多: 10字 ngram 最大重复 {repeated}")

    copy_hits: list[str] = []
    if source_samples:
        copy_hits = copy_risk_hits(
            draft,
            source_samples,
            n=int(validation.get("copy_check_ngram_chars", 34)),
        )
        if copy_hits:
            issues.append(f"疑似复用语料长片段: {len(copy_hits)} 处")

    score = 5.0 - min(4.0, len(issues) * 0.8)
    return {
        "score": round(max(0.0, score) * 2) / 2,
        "confirmed": not issues,
        "issues": issues,
        "visible_chars": length,
        "repeated_10gram_max": repeated,
        "copy_hits": copy_hits,
    }
