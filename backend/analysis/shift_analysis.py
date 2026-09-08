"""Shift Scheduler の分析(DataFrame → DataFrame の純粋関数)。

Phase 3-8 で作った `analysis/` に Phase 6 が足す 1 モジュール(移設・作り直しはしない)。
shift の benchmark を「規模別」に回して貯めた `benchmark_runs` を読み、

  - 手実装(Greedy / Backtracking / B&B)が規模を上げるとどこで現実的な時間に収まらなくなるか
  - どの規模で CP-SAT に切り替えるべきか(crossover)
  - 多目的(labor_cost × day_off_satisfaction)の Pareto フロント

を出す。`analysis/` は app から切り離した dev トラック(pandas / matplotlib は dev 依存。
`app` からは import しない。設計は `Phase-3-8.md`)。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analysis.loaders import load_benchmark_runs

_HANDWRITTEN = "handwritten"
# 「破綻」を見るのは厳密な手実装だけ ── Greedy は多項式時間だが解が最適でない
_EXACT_HANDWRITTEN = ("backtracking", "branch_and_bound")


def load_shift_benchmark_runs(path: str | Path) -> pd.DataFrame:
    """`load_benchmark_runs` に、各 run の問題規模の列を足したもの。

    size … スタッフ数 × スロット数(割当変数の目安)
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
        size_by_id[rec["id"]] = len(data["staff"]) * len(data["slots"])

    df = df[df["problem_type"] == "shift_scheduling"].copy()
    df["size"] = df["benchmark_id"].map(lambda i: size_by_id.get(i, 0))
    return df


def by_size(df: pd.DataFrame, *, value: str = "elapsed_ms_median") -> pd.DataFrame:
    """size × (algorithm, implementation) で value を median 集約したロング表。"""
    if "size" not in df.columns:
        raise KeyError("'size' 列が無い ── load_shift_benchmark_runs で読む")
    return (
        df.groupby(["size", "algorithm", "implementation"])[value]
        .median()
        .reset_index()
        .sort_values(["algorithm", "size"])
        .reset_index(drop=True)
    )


def handwritten_vs_cpsat(df: pd.DataFrame, *, metric: str = "elapsed_ms_median") -> pd.DataFrame:
    """厳密な手実装(backtracking / B&B)と CP-SAT を size ごとに横並べ、speedup(手/CP-SAT)。"""
    long = by_size(df, value=metric)
    hw = (
        long[
            (long["implementation"] == _HANDWRITTEN) & (long["algorithm"].isin(_EXACT_HANDWRITTEN))
        ]
        .groupby("size")[metric]
        .min()  # 厳密な手実装のうち最速のもの(通常 B&B)
        .rename("handwritten")
    )
    lib = (
        long[long["implementation"].str.startswith("library")]
        .groupby("size")[metric]
        .min()
        .rename("cp_sat")
    )
    out = pd.concat([hw, lib], axis=1).reset_index()
    if "handwritten" in out.columns and "cp_sat" in out.columns:
        out["speedup"] = out["handwritten"] / out["cp_sat"]
    return out


def crossover_size(df: pd.DataFrame, *, metric: str = "elapsed_ms_median") -> float | None:
    """CP-SAT がはじめて手実装より速くなる size。無ければ None。"""
    table = handwritten_vs_cpsat(df, metric=metric).sort_values("size")
    if "speedup" not in table.columns:
        return None
    faster = table[table["speedup"] > 1.0]
    return float(faster["size"].iloc[0]) if not faster.empty else None


def pareto_front(
    df: pd.DataFrame,
    *,
    minimize: str = "metrics.labor_cost",
    maximize: str = "metrics.day_off_satisfaction",
) -> pd.DataFrame:
    """(minimize を小さく、maximize を大きく)で他に支配されない run/algorithm 行だけ残す。"""
    cols = [
        c for c in ("size", "algorithm", "implementation", minimize, maximize) if c in df.columns
    ]
    pts = df.dropna(subset=[minimize, maximize])[cols].reset_index(drop=True)
    keep: list[int] = []
    for i, row in pts.iterrows():
        dominated = (
            (pts[minimize] <= row[minimize])
            & (pts[maximize] >= row[maximize])
            & ((pts[minimize] < row[minimize]) | (pts[maximize] > row[maximize]))
        ).any()
        if not dominated:
            keep.append(int(i))
    return pts.loc[keep].sort_values(minimize).reset_index(drop=True)
