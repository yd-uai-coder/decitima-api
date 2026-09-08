"""measure_call ── 任意の callable を N 回実行して実行時間・メモリを集計する汎用計測。

ベンチマーク(Phase 3)の測定コア。ドメインに依存しない(テンプレート還元候補)。

- 実行時間: `time.perf_counter` で 1 回ずつ計測し、numpy で中央値・四分位。
- メモリ: `tracemalloc` のピーク(プロセス全体。ベンチマークは strategy を直列に回すので
  他の解の割当と混ざらない)。
- 操作回数(`_ops`)は各アルゴリズムが `solve()` 内で数えるものなので、ここでは扱わない。

「測定を仕込む場所」= solve の外。
"""

from __future__ import annotations

import time
import tracemalloc
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

# measure_callの戻り値型
@dataclass(frozen=True)
class Measurement:
    """1 つの callable を runs 回実行した実測の集計。時間はミリ秒、メモリは KB。"""

    runs: int  # 実行回数(measure_call の runs 引数と同じ)
    elapsed_ms_median: float  # 実行時間の中央値(ミリ秒)。ベンチの代表値
    elapsed_ms_p25: float  # 実行時間の第 1 四分位点(ミリ秒)。ばらつきの下側
    elapsed_ms_p75: float  # 第 3 四分位点(ミリ秒)。ばらつきの上側
    peak_memory_kb: float  # runs 回で最大のピークメモリ(KB)

# 計測の1回分を切り出し -> measure_call関数内で使用する
def _timed_call[T](fn: Callable[[], T]) -> tuple[T, float, float]:
    """fn() を 1 回実行し、(戻り値, 経過ミリ秒, ピークメモリ KB) を返す。"""
    tracemalloc.start()
    start = time.perf_counter()
    result = fn()
    elapsed_ms = (time.perf_counter() - start) * 1000.0
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return result, elapsed_ms, peak_bytes / 1024.0

# _timed_callを反復呼び出し
def measure_call[T](fn: Callable[[], T], runs: int) -> tuple[T, Measurement]:
    """fn() を runs 回実行し、最後の戻り値と実測の集計を返す。

    fn は引数なしの呼び出し可能オブジェクト(通常は `lambda: strategy.solve(problem)`)。
    純粋関数を渡す前提 ── 戻り値は毎回同じなので代表値として「最後の 1 つ」を返す。
    """
    if runs < 1:
        raise ValueError(f"runs must be >= 1, got {runs}")

    # 1 回目でここで result を確定(runs >= 1 は保証済み。pyright の未束縛警告も避ける)
    result, first_ms, first_kb = _timed_call(fn)
    elapsed_ms: list[float] = [first_ms]
    peak_kb: list[float] = [first_kb]
    for _ in range(runs - 1):
        result, ms, kb = _timed_call(fn)
        elapsed_ms.append(ms)
        peak_kb.append(kb)

    arr = np.array(elapsed_ms)
    return result, Measurement(
        runs=runs,
        elapsed_ms_median=float(np.median(arr)),
        elapsed_ms_p25=float(np.percentile(arr, 25)),
        elapsed_ms_p75=float(np.percentile(arr, 75)),
        peak_memory_kb=max(peak_kb),
    )
