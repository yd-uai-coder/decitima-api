"""作業単位 4-8: analysis/route_benchmark.py(分析トラック)。

対象 = DataFrame → DataFrame の純粋関数。ドライバ = このテスト関数。スタブ不要
(`analysis/` は app から切り離した純粋レイヤー ── `Phase-3-8.md`)。
"""

from pathlib import Path

import pandas as pd

from analysis.route_benchmark import (
    by_size,
    crossover_size,
    handwritten_vs_library,
    load_route_benchmark_runs,
)

_SAMPLE = Path(__file__).parents[2] / "analysis" / "data" / "sample_route_benchmark_runs.jsonl"


def _fake_df() -> pd.DataFrame:
    """size × implementation を振った最小の flat DataFrame。"""
    rows = []
    for size, hw, lib in [(10, 2.0, 5.0), (100, 8.0, 6.0), (1000, 40.0, 12.0)]:
        rows.append(
            {
                "size": size,
                "algorithm": "dijkstra",
                "implementation": "handwritten",
                "elapsed_ms_median": hw,
            }
        )
        rows.append(
            {
                "size": size,
                "algorithm": "dijkstra",
                "implementation": "library:networkx",
                "elapsed_ms_median": lib,
            }
        )
    return pd.DataFrame(rows)


def test_by_size_is_long_and_sorted() -> None:
    out = by_size(_fake_df())
    assert list(out.columns) == ["size", "algorithm", "implementation", "elapsed_ms_median"]
    # (algorithm, size) でソート ── 同一アルゴリズムなら size 昇順、実装は隣り合う
    assert list(out["size"]) == [10, 10, 100, 100, 1000, 1000]


def test_handwritten_vs_library_computes_speedup() -> None:
    out = handwritten_vs_library(_fake_df())
    row_1000 = out[out["size"] == 1000].iloc[0]
    assert row_1000["speedup"] == 40.0 / 12.0  # handwritten / library


def test_crossover_size_finds_first_size_library_wins() -> None:
    # size 100 で library(6.0)が handwritten(8.0)を初めて上回る
    assert crossover_size(_fake_df()) == {"dijkstra": 100.0}


def test_crossover_none_when_handwritten_always_wins() -> None:
    df = _fake_df()
    df.loc[df["implementation"] == "library:networkx", "elapsed_ms_median"] = 999.0
    assert crossover_size(df) == {"dijkstra": None}


def test_fixed_sample_loads_with_size_and_density() -> None:
    df = load_route_benchmark_runs(_SAMPLE)
    assert not df.empty
    assert {"size", "density"} <= set(df.columns)
    assert df["size"].min() >= 2
    # networkx の dijkstra エントリが含まれている
    assert "library:networkx" in set(df["implementation"])


def test_plot_smoke() -> None:
    import matplotlib

    matplotlib.use("Agg")
    from matplotlib.figure import Figure

    from analysis.plots import plot_handwritten_vs_library

    pivot = handwritten_vs_library(load_route_benchmark_runs(_SAMPLE))
    assert isinstance(plot_handwritten_vs_library(pivot), Figure)
