"""作業単位 3-8: analysis.benchmark_report。

対象 = `by_algorithm` / `input_size_curve` / `regression`(DataFrame → DataFrame の純粋関数)。
ドライバ = このテスト関数(手組み DataFrame)。**スタブ不要**。
"""

import pandas as pd
import pytest

from analysis.benchmark_report import by_algorithm, input_size_curve, regression


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _row(algo: str, ms: float, ops: int, mem: float = 1.0) -> dict:
    return {
        "algorithm": algo,
        "elapsed_ms_median": ms,
        "peak_memory_kb": mem,
        "operation_count": ops,
        "quality_ratio": 1.0,
    }


_ROWS = [
    _row("dijkstra", 0.10, 4),
    _row("dijkstra", 0.12, 4),
    _row("brute_force", 0.50, 40, mem=2.0),
]


def test_by_algorithm_medians_and_counts() -> None:
    out = by_algorithm(_df(_ROWS)).set_index("algorithm")
    assert out.loc["dijkstra", "elapsed_ms_median"] == pytest.approx(0.11)
    assert out.loc["dijkstra", "n_entries"] == 2
    assert out.loc["brute_force", "operation_count"] == 40


def test_by_algorithm_respects_stat_arg() -> None:
    out = by_algorithm(_df(_ROWS), stat="max").set_index("algorithm")
    assert out.loc["dijkstra", "elapsed_ms_median"] == pytest.approx(0.12)


def test_input_size_curve_pivots_size_by_algorithm() -> None:
    rows = [
        {"size": 4, "algorithm": "dijkstra", "operation_count": 3},
        {"size": 4, "algorithm": "brute_force", "operation_count": 6},
        {"size": 8, "algorithm": "dijkstra", "operation_count": 7},
        {"size": 8, "algorithm": "brute_force", "operation_count": 200},
    ]
    curve = input_size_curve(_df(rows))
    assert list(curve["size"]) == [4, 8]
    assert curve.set_index("size").loc[8, "brute_force"] == 200


def test_input_size_curve_requires_size_column() -> None:
    with pytest.raises(KeyError):
        input_size_curve(_df(_ROWS))


def test_regression_computes_ratio_and_pct() -> None:
    base = _df([{"algorithm": "dijkstra", "elapsed_ms_median": 0.10}])
    cur = _df([{"algorithm": "dijkstra", "elapsed_ms_median": 0.12}])
    out = regression(base, cur).set_index("algorithm")
    assert out.loc["dijkstra", "ratio"] == pytest.approx(1.2)
    assert out.loc["dijkstra", "pct_change"] == pytest.approx(20.0)
