"""作業単位 6-7: analysis/shift_analysis.py(分析トラック)。

対象 = DataFrame → DataFrame の純粋関数。ドライバ = このテスト関数。スタブ不要
(`analysis/` は app から切り離した純粋レイヤー ── `Phase-3-8.md`)。
"""

from pathlib import Path

import pandas as pd

from analysis.shift_analysis import (
    by_size,
    crossover_size,
    handwritten_vs_cpsat,
    load_shift_benchmark_runs,
    pareto_front,
)

_SAMPLE = Path(__file__).parents[2] / "analysis" / "data" / "sample_shift_runs.jsonl"


def _fake_df() -> pd.DataFrame:
    rows = []
    for size, hw, cp in [(6, 1.0, 12.0), (18, 20.0, 18.0), (60, 400.0, 40.0)]:
        rows += [
            {
                "size": size,
                "algorithm": "backtracking",
                "implementation": "handwritten",
                "elapsed_ms_median": hw,
                "metrics.labor_cost": size * 900.0,
                "metrics.day_off_satisfaction": 1.0,
            },
            {
                "size": size,
                "algorithm": "cp_sat",
                "implementation": "library:ortools",
                "elapsed_ms_median": cp,
                "metrics.labor_cost": size * 900.0,
                "metrics.day_off_satisfaction": 1.0,
            },
        ]
    return pd.DataFrame(rows)


def test_by_size_is_long_and_sorted() -> None:
    out = by_size(_fake_df())
    assert list(out.columns) == ["size", "algorithm", "implementation", "elapsed_ms_median"]
    assert list(out["size"]) == [6, 18, 60, 6, 18, 60]


def test_handwritten_vs_cpsat_computes_speedup() -> None:
    out = handwritten_vs_cpsat(_fake_df())
    row = out[out["size"] == 60].iloc[0]
    assert row["speedup"] == 400.0 / 40.0


def test_crossover_size_is_first_size_cpsat_wins() -> None:
    # size 18 で CP-SAT(18.0)が手実装(20.0)を初めて上回る
    assert crossover_size(_fake_df()) == 18.0


def test_crossover_none_when_handwritten_always_wins() -> None:
    df = _fake_df()
    df.loc[df["implementation"] == "library:ortools", "elapsed_ms_median"] = 9999.0
    assert crossover_size(df) is None


def test_pareto_front_keeps_non_dominated() -> None:
    df = pd.DataFrame(
        [
            {"algorithm": "a", "metrics.labor_cost": 100.0, "metrics.day_off_satisfaction": 1.0},
            {"algorithm": "b", "metrics.labor_cost": 120.0, "metrics.day_off_satisfaction": 1.0},
            {"algorithm": "c", "metrics.labor_cost": 90.0, "metrics.day_off_satisfaction": 0.5},
        ]
    )
    front = pareto_front(df)
    assert set(front["algorithm"]) == {"a", "c"}  # b は a に支配される


def test_fixed_sample_loads_with_size() -> None:
    df = load_shift_benchmark_runs(_SAMPLE)
    assert not df.empty
    assert "size" in df.columns
    assert set(df["implementation"]) >= {"handwritten", "library:ortools"}
    assert crossover_size(df) is not None  # サンプルは手実装が破綻する規模を含む
