# DeciTima samples │ Phase 10
"""二分探索の応用 ──「値を探す」から「答えを探す」へ。

binary_search(`app/algorithms/search/binary_search.py`)は、ソート済みの列から
target と等しい要素を探す(「値の探索」)。ここでの find_threshold は、ある整数パラメータに
ついて evaluate(param) が単調に変化することを前提に、条件を満たす最小のパラメータを探す
(「答えを二分探索する」── 競技プログラミングで binary search on the answer と呼ばれる技法)。

前提: evaluate は [low, high] 上で単調(mode="at_most" なら非増加、"at_least" なら非減少)。
前提が崩れる入力では、実際の境界とは異なる値を返しうる(単調性の検証は evaluate を全件
呼ぶのと同じコストなので、ここでは検証しない ── 呼び出し側が前提を保証する)。

複雑さ: 全件スイープは O(high-low) 回の evaluate、こちらは O(log(high-low)) 回。
evaluate 1 回が重い(例: 1 回の solve)ほど二分探索の価値が上がる ── これが Phase 10 の
「感度分析」章の核。

registry には載せない素の純粋関数(floyd_warshall / knapsack_2d と同型)。
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Literal


def find_threshold(
    low: int,
    high: int,
    evaluate: Callable[[int], float],
    *,
    target: float,
    mode: Literal["at_most", "at_least"] = "at_most",
) -> int | None:
    """[low, high] の整数のうち、evaluate(param) が target 条件を満たす最小の param を返す。
    範囲内に条件を満たす点が無ければ None。

    時間 O(log(high-low)) 回の evaluate 呼び出し / 空間 O(1)。
    """
    if low > high:
        raise ValueError(f"low({low}) must be <= high({high})")
    # mode に応じて「条件を満たす」の意味を決める
    satisfies = (
        (lambda value: value <= target) if mode == "at_most" else (lambda value: value >= target)
    )

    # high でも満たさなければ、単調性の前提のもとでは範囲内に条件を満たす点は無い
    if not satisfies(evaluate(high)):
        return None

    lo, hi = low, high
    while lo < hi:
        # mid は現在の探索区間の中央。桁溢れを避ける書き方(Phase 1 binary_search と同じ)
        mid = lo + (hi - lo) // 2
        if satisfies(evaluate(mid)):
            hi = mid  # mid が条件を満たす → 答えは mid 以下にある
        else:
            lo = mid + 1  # mid が満たさない → 答えは mid より大きい
    return lo
