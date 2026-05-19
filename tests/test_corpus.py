from __future__ import annotations

from auto_novel_writer.corpus import spread_indexes


def test_spread_indexes_edges() -> None:
    assert spread_indexes(0, 3) == []
    assert spread_indexes(5, 0) == []
    assert spread_indexes(3, 5) == [0, 1, 2]


def test_spread_indexes_spreads_across_range() -> None:
    assert spread_indexes(10, 3) == [0, 4, 9]
