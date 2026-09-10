# DeciTima samples │ Phase 7
"""作業単位 7-2: knapsack_2d(純粋関数)。

テスト対象 / ドライバ / スタブ:
- 対象: `knapsack_2d`(純粋関数)
- ドライバ: このテスト関数(素のタプルリストを直接渡す)
- スタブ: 不要 ── 純粋で外部依存を呼ばない(`Phase-0-3.md` の純粋レイヤー)

`KnapsackDpTravelStrategy`(`knapsack.py` の 7-4 分)のテストは 7-4 で `test_travel_common.py` に。
"""

from __future__ import annotations

from app.algorithms.optimization.knapsack import knapsack_2d


def test_knapsack_2d_picks_best_value_under_both_caps() -> None:
    # item0 (2,3,10) / item1 (3,2,12) / item2 (4,4,15)
    # cap (5,5): 0+1 は cost5,time5 で価値22 > item2 単体15
    assert set(knapsack_2d([(2, 3, 10.0), (3, 2, 12.0), (4, 4, 15.0)], 5, 5)) == {0, 1}


def test_knapsack_2d_respects_the_tighter_capacity() -> None:
    # 時間の方が厳しい: cap (10, 2)。item1 (3,2,12) だけ入る
    assert knapsack_2d([(2, 3, 10.0), (3, 2, 12.0)], 10, 2) == [1]


def test_knapsack_2d_zero_or_negative_cap() -> None:
    assert knapsack_2d([(1, 1, 5.0)], 0, 0) == []
    assert knapsack_2d([(1, 1, 5.0)], -1, 5) == []


def test_knapsack_2d_is_0_1_not_unbounded() -> None:
    # 同じアイテムを 2 回取れれば価値 20 だが 0/1 なので 1 回だけ = 10
    assert knapsack_2d([(1, 1, 10.0)], 5, 5) == [0]
