"""作業単位 6-2: スケジューリング・プリミティブ(sliding_window / difference_array)。

対象 = 純粋関数。ドライバ = このテスト関数。スタブ不要。
これらは `scheduling/common.py` と各 strategy の写経ミスの第一の番人(#15)。
"""

from app.algorithms.patterns.difference_array import range_add
from app.algorithms.patterns.sliding_window import (
    max_consecutive_days,
    run_length_at,
    to_ordinal,
)

# --- sliding_window ---------------------------------------------------------


def test_max_consecutive_days_counts_unbroken_run() -> None:
    days = ["2026-09-01", "2026-09-02", "2026-09-03", "2026-09-05"]
    assert max_consecutive_days(days) == 3  # 01-02-03 が連続、05 で途切れる


def test_max_consecutive_days_empty_is_zero() -> None:
    assert max_consecutive_days([]) == 0


def test_run_length_at_expands_both_directions() -> None:
    present = {10, 11, 12, 14}
    assert run_length_at(present, 11) == 3  # 10-11-12
    assert run_length_at(present, 14) == 1


def test_run_length_at_is_the_incremental_check() -> None:
    # Backtracking: 既存 {d, d+1} に d+2 を足すと連続 3
    ords = {to_ordinal("2026-09-01"), to_ordinal("2026-09-02")}
    new = to_ordinal("2026-09-04")
    assert run_length_at(ords | {new}, 739860) == 2
    assert run_length_at(ords | {new}, new) == 1


# --- difference_array (imos 法) --------------------------------------------


def test_range_add_applies_interval_deltas() -> None:
    # [1,3) に +2、[2,4) に +1
    out = range_add(5, [(1, 3, 2.0), (2, 4, 1.0)])
    assert out == [0.0, 2.0, 3.0, 1.0, 0.0]


def test_range_add_clamps_out_of_range() -> None:
    assert range_add(3, [(-1, 10, 1.0)]) == [1.0, 1.0, 1.0]


def test_range_add_ignores_empty_interval() -> None:
    assert range_add(3, [(2, 2, 5.0)]) == [0.0, 0.0, 0.0]
