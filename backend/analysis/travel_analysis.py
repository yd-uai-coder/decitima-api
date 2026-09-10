# DeciTima samples │ Phase 7
"""作業単位 7-6: Travel Planner の分析(DataFrame → DataFrame の純粋関数)。

Phase 3-8 で作った `analysis/` に Phase 7 が足す 1 モジュール(移設・作り直しはしない)。
travel_planning の benchmark を「訪問候補数(規模)別」に回して貯めた `benchmark_runs` を読み、

  - Knapsack DP(移動を無視した上界)と Greedy(移動込みで逐次)で
    「解の価値」がどれだけ食い違うか(dp_vs_greedy)
  - 規模を上げると DP の「移動無視」がどこで invalid を生むか

を出す。`analysis/` は app から切り離した dev トラック(pandas / matplotlib は dev 依存。
`app` からは import しない。設計は `Phase-3-8.md`)。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analysis.loaders import load_benchmark_runs


def load_travel_benchmark_runs(path: str | Path) -> pd.DataFrame:
    """`load_benchmark_runs` に、各 run の訪問候補数の列を足したもの。

    size … place 数(start を含む。選択変数の目安)
    """
    df = load_benchmark_runs(path)
    if df.empty:
        return df

    size_by_id: dict[str, int] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        payload = rec["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        data = payload["problem"]["data"]
        size_by_id[rec["id"]] = len(data["places"])

    df = df[df["problem_type"] == "travel_planning"].copy()
    df["size"] = df["benchmark_id"].map(lambda i: size_by_id.get(i, 0))
    return df


def by_size(df: pd.DataFrame, *, value: str = "elapsed_ms_median") -> pd.DataFrame:
    """size × algorithm で value を median 集約したロング表。"""
    if "size" not in df.columns:
        raise KeyError("'size' 列が無い ── load_travel_benchmark_runs で読む")
    return (
        df.groupby(["size", "algorithm"])[value]
        .median()
        .reset_index()
        .sort_values(["algorithm", "size"])
        .reset_index(drop=True)
    )


def dp_vs_greedy(df: pd.DataFrame, *, value: str = "metrics.total_value") -> pd.DataFrame:
    """size ごとに Knapsack DP と Greedy の指標を横並べ、gap(dp − greedy)を出す。

    DP は移動を無視した上界なので `metrics.total_value` は Greedy 以上になりがち。
    ただし DP の解は移動込みだと予算超過(invalid)のことがある ── それは
    `hard_violations` / `solution_status` 列で見る。
    """
    long = by_size(df, value=value)
    dp = long[long["algorithm"] == "knapsack_dp"].set_index("size")[value].rename("knapsack_dp")
    gr = long[long["algorithm"] == "greedy"].set_index("size")[value].rename("greedy")
    out = pd.concat([dp, gr], axis=1).reset_index()
    if "knapsack_dp" in out.columns and "greedy" in out.columns:
        out["gap"] = out["knapsack_dp"] - out["greedy"]
    return out


def invalid_rate_by_size(df: pd.DataFrame) -> pd.DataFrame:
    """size × algorithm で「invalid だった run の割合」。DP が規模で崩れるのを見る。"""
    if "solution_status" not in df.columns:
        raise KeyError("'solution_status' 列が無い ── load_benchmark_runs の出力を渡す")
    g = df.assign(_invalid=(df["solution_status"] == "invalid").astype(float))
    return (
        g.groupby(["size", "algorithm"])["_invalid"]
        .mean()
        .reset_index()
        .rename(columns={"_invalid": "invalid_rate"})
        .sort_values(["algorithm", "size"])
        .reset_index(drop=True)
    )
