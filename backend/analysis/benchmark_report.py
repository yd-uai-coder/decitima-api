"""benchmark DataFrame の集計(DataFrame → DataFrame の純粋関数)。

`load_benchmark_runs` が返す flat DataFrame を入力に、比較しやすい形へまとめる。
benchmark 専用モジュール ── 後続 Phase は `analysis/shift_analysis.py`(Phase 5)や
`analysis/experiment.py`(Phase 13)を横に並べる。
"""

from __future__ import annotations

import pandas as pd

# time / memory は直接比較できるが、operation_count はアルゴリズム定義の単位なので
# 「内部仕事量」としてのみ読む(Phase-3-1 / Phase-3-2 参照)
_METRIC_COLS = ["elapsed_ms_median", "peak_memory_kb", "operation_count", "quality_ratio"]


def by_algorithm(df: pd.DataFrame, *, stat: str = "median") -> pd.DataFrame:
    """アルゴリズム別に各指標を集約する(1 アルゴリズム 1 行)。

    stat: "median" / "mean" / "max" 等、pandas の集約名。observations は n_entries に。
    """
    cols = [c for c in _METRIC_COLS if c in df.columns]
    agg = df.groupby("algorithm")[cols].agg(stat)
    agg["n_entries"] = df.groupby("algorithm").size()
    return agg.reset_index()


def input_size_curve(
    df: pd.DataFrame, *, size_col: str = "size", value: str = "operation_count"
) -> pd.DataFrame:
    """size × algorithm の `value` ピボット(入力サイズ別カーブのデータ源)。

    df は `size_col` 列を含む必要がある ── benchmark を複数サイズで回して concat し、
    各行に問題サイズを付けたもの。
    """
    if size_col not in df.columns:
        raise KeyError(
            f"{size_col!r} not in df; benchmark を複数サイズで回して {size_col} 列を付けてから呼ぶ"
        )
    return (
        df.pivot_table(index=size_col, columns="algorithm", values=value, aggfunc="median")
        .reset_index()
        .rename_axis(columns=None)
    )


def regression(
    baseline: pd.DataFrame, current: pd.DataFrame, *, metric: str = "elapsed_ms_median"
) -> pd.DataFrame:
    """同一アルゴリズムの baseline → current の変化。ratio > 1 なら遅く / 重くなった。"""
    b = by_algorithm(baseline).set_index("algorithm")[metric]
    c = by_algorithm(current).set_index("algorithm")[metric]
    out = pd.DataFrame({"baseline": b, "current": c})
    out["ratio"] = out["current"] / out["baseline"]
    out["pct_change"] = (out["ratio"] - 1.0) * 100.0
    return out.reset_index()
