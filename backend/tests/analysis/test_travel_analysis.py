# DeciTima samples │ Phase 7
"""作業単位 7-6: analysis/travel_analysis.py(分析トラック)。

対象 = DataFrame → DataFrame の純粋関数。ドライバ = このテスト関数。スタブ不要
(`analysis/` は app から切り離した純粋レイヤー ── `Phase-3-8.md`)。
"""

from pathlib import Path

import pandas as pd

from analysis.travel_analysis import (
    by_size,
    dp_vs_greedy,
    invalid_rate_by_size,
    load_travel_benchmark_runs,
)

_SAMPLE = Path(__file__).parents[2] / "analysis" / "data" / "sample_travel_runs.jsonl"


def _fake_df() -> pd.DataFrame:
    """size × algorithm を振った最小の flat DataFrame。"""
    rows = []
    for size, dp_val, gr_val, dp_status in [
        (5, 35.0, 35.0, "valid"),
        (6, 35.0, 13.0, "invalid"),
        (12, 75.0, 55.0, "invalid"),
    ]:
        rows.append(
            {
                "size": size,
                "algorithm": "knapsack_dp",
                "solution_status": dp_status,
                "elapsed_ms_median": 1.0,
                "metrics.total_value": dp_val,
            }
        )
        rows.append(
            {
                "size": size,
                "algorithm": "greedy",
                "solution_status": "valid",
                "elapsed_ms_median": 3.0,
                "metrics.total_value": gr_val,
            }
        )
    return pd.DataFrame(rows)


def test_by_size_is_long_and_sorted() -> None:
    out = by_size(_fake_df())
    assert list(out.columns) == ["size", "algorithm", "elapsed_ms_median"]
    assert list(out["size"]) == [5, 6, 12, 5, 6, 12]


def test_dp_vs_greedy_computes_gap() -> None:
    out = dp_vs_greedy(_fake_df())
    row = out[out["size"] == 6].iloc[0]
    assert row["knapsack_dp"] == 35.0
    assert row["greedy"] == 13.0
    assert row["gap"] == 22.0  # DP は移動を無視した「幻の価値」


def test_invalid_rate_by_size_flags_dp_overrun() -> None:
    out = invalid_rate_by_size(_fake_df())
    dp = out[out["algorithm"] == "knapsack_dp"].set_index("size")["invalid_rate"]
    assert dp.loc[5] == 0.0
    assert dp.loc[6] == 1.0
    greedy = out[out["algorithm"] == "greedy"]["invalid_rate"]
    assert (greedy == 0.0).all()


def test_fixed_sample_loads_with_size() -> None:
    df = load_travel_benchmark_runs(_SAMPLE)
    assert not df.empty
    assert "size" in df.columns
    assert set(df["algorithm"]) >= {"knapsack_dp", "greedy"}
    # サンプルは「DP は移動を無視するので予算がきつい規模で invalid」を含む
    rates = invalid_rate_by_size(df)
    dp_rates = rates[rates["algorithm"] == "knapsack_dp"]["invalid_rate"]
    assert dp_rates.max() == 1.0
    assert dp_rates.min() == 0.0
