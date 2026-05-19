from __future__ import annotations

from auto_novel_writer.config import deep_merge


def test_deep_merge_nested_override() -> None:
    base = {"a": {"b": 1, "c": 2}, "d": 3}
    override = {"a": {"b": 9}}
    assert deep_merge(base, override) == {"a": {"b": 9, "c": 2}, "d": 3}
