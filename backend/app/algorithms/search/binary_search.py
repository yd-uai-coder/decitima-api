"""二分探索(プリミティブ)

昇順ソート済みの列を前提に、探索範囲を毎回半分にする。前提が崩れると誤った
結果を返すので、テストや assert 用に is_sorted_ascending を併せて用意する。
registry には載せない素の純粋関数。
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Protocol


class _Comparable(Protocol):
    # other を Any にしておくと int / str / float などの組み込み比較型が満たせる
    # 仮にObject の場合はpyrightで警告が出る。
    def __lt__(self, other: Any, /) -> bool: ...


def binary_search[C: _Comparable](seq: Sequence[C], target: C) -> int:
    """昇順ソート済みの seq から target の添字を返す。無ければ -1。

    時間 O(log n) / 空間 O(1)。lo / hi は探索中の閉区間 [lo, hi] の両端。
    """
    lo, hi = 0, len(seq) - 1
    while lo <= hi:
        # mid は現在の探索区間の中央。桁溢れを避ける書き方
        mid = lo + (hi - lo) // 2
        if seq[mid] == target:
            return mid
        # target が中央より大きければ右半分、小さければ左半分に絞る
        if seq[mid] < target:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1


def is_sorted_ascending[C: _Comparable](seq: Sequence[C]) -> bool:
    """binary_search の前提(昇順)を満たすか。"""
    # 「次の要素が前の要素より小さい」箇所が1つも無ければ昇順
    return not any(seq[i + 1] < seq[i] for i in range(len(seq) - 1))
