"""Difference Array(差分法 / imos 法)── プリミティブ。

「区間 [l, r) に一律 +delta」を **O(1)** で記録し、最後に 1 回の累積和で全要素を確定する。
naive に毎区間ループすると O(区間数 × 幅)、imos 法なら O(区間数 + サイズ)。累積和(Prefix Sum)の対。

Shift Scheduler では **時間帯別の在籍人数**に使う ── 各スロットが [start_hour, end_hour) を
カバーするので、割り当てられたスロットぶんだけ区間加算し、時刻ごとの在籍人数配列を得る。
`scheduling/common.on_duty_by_hour` が消費する。

registry には載らない。
"""

from __future__ import annotations

from collections.abc import Iterable


def range_add(size: int, updates: Iterable[tuple[int, int, float]]) -> list[float]:
    """updates の各 (l, r, delta) を「[l, r) に +delta」として適用し、長さ size の配列を返す。

    imos 法: diff[l] += delta / diff[r] -= delta を記録 → 累積和で復元。
    範囲外や l >= r の update は無視する。
    """
    diff = [0.0] * (size + 1)
    for left, right, delta in updates:
        left = max(left, 0)
        right = min(right, size)
        if left >= right:
            continue
        diff[left] += delta
        diff[right] -= delta
    out: list[float] = []
    running = 0.0
    for i in range(size):
        running += diff[i]
        out.append(running)
    return out
