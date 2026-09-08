"""線形探索(プリミティブ)。"""
from __future__ import annotations

from collections.abc import Sequence


def linear_search[T](seq: Sequence[T], target: T) -> int:
    """seq を先頭から走査し、target と等しい最初の要素の添字を返す。無ければ -1。"""
    for i, value in enumerate(seq):
        if value == target:
            return i
    return -1
