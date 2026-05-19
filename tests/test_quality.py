from __future__ import annotations

from auto_novel_writer.quality import copy_risk_hits, deterministic_chapter_check, repeated_ngram_count


def test_repeated_ngram_count_detects_repetition() -> None:
    assert repeated_ngram_count("天地玄黄天地玄黄天地玄黄", n=4) >= 3


def test_copy_risk_hits_detects_shared_long_phrase() -> None:
    draft = "这是原创开头，但这里有一段非常独特的连续文字用于检测。"
    samples = [{"content": "别的内容。一段非常独特的连续文字用于检测。更多内容"}]
    assert copy_risk_hits(draft, samples, n=12)


def test_deterministic_check_flags_forbidden_phrase() -> None:
    config = {
        "validation": {
            "forbidden_phrases": ["作为AI"],
            "min_chapter_chars": 1,
            "max_repeated_ngrams": 99,
            "copy_check_ngram_chars": 20,
        }
    }
    result = deterministic_chapter_check("作为AI，我不能这样写。", config)
    assert result["issues"]
