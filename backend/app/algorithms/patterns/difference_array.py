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
    """imos 法: diff[l] += delta / diff[r] -= delta を記録 → 累積和で復元。
    size:最終的に作る配列の長さ
    updates:
        left:開始インデックス
        right:終了インデックス
        delta:加算値
    diff:

    範囲外や l >= r の update は無視する。
    updates の各 (l, r, delta) を「[l, r) に +delta」として適用し、長さ size の配列を返す。
    """

    diff = [0.0] * (size + 1) #引数のleft,rightとdiffのインデックス番号を合わせたいからsize + 1
    for left, right, delta in updates:
        left = max(left, 0)         # 加算位置の左端は0以上
        right = min(right, size)    # 加算位置の右端はsize以下
        if left >= right:           # 論理チェック
            continue
        diff[left] += delta         # 加算開始
        diff[right] -= delta        # 元に戻す
    out: list[float] = []
    running = 0.0

    # return用配列を作る
    for i in range(size):
        running += diff[i]
        out.append(running)
    return out
