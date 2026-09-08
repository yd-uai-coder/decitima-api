"""Route Benchmark の集計(DataFrame → DataFrame の純粋関数)。

Phase 3-8 で作った `analysis/` に Phase 4 が足す1モジュール(移設・作り直しはしない)。
route_planning の benchmark を「サイズ・密度別」に回して貯めた `benchmark_runs` を読み、
「手実装トラックは n がいくつを超えると networkx に負けるか」を出す。

`analysis/` は app から切り離した dev トラック(pandas / matplotlib は dev 依存。
`app` からは import しない。設計は `Phase-3-8.md`)。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analysis.loaders import load_benchmark_runs


def load_route_benchmark_runs(path: str | Path) -> pd.DataFrame:
    """`load_benchmark_runs` に、各 run の問題サイズ・密度の列を足したもの。

    size    … ノード数
    density … (エッジ数 - (size - 1)) / size ── 連鎖を超えた「横エッジ」の割合
    """
    df = load_benchmark_runs(path)
    if df.empty:
        return df

    shape: dict[str, tuple[int, float]] = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        rec = json.loads(line)
        payload = rec["payload"]
        if isinstance(payload, str):
            payload = json.loads(payload)
        data = payload["problem"]["data"]
        n = len(data["nodes"])
        extra = len(data["edges"]) - max(n - 1, 0)
        shape[rec["id"]] = (n, round(extra / n, 3) if n else 0.0)

    df["size"] = df["benchmark_id"].map(lambda i: shape.get(i, (0, 0.0))[0])
    df["density"] = df["benchmark_id"].map(lambda i: shape.get(i, (0, 0.0))[1])
    return df


def by_size(df: pd.DataFrame, *, value: str = "elapsed_ms_median") -> pd.DataFrame:
    """size × (algorithm, implementation) で value を median 集約したロング表。"""
    if "size" not in df.columns:
        raise KeyError("'size' 列が無い ── load_route_benchmark_runs で読む")
    return (
        df.groupby(["size", "algorithm", "implementation"])[value]
        .median()
        .reset_index()
        .sort_values(["algorithm", "size"])
        .reset_index(drop=True)
    )


def handwritten_vs_library(df: pd.DataFrame, *, metric: str = "elapsed_ms_median") -> pd.DataFrame:
    """同名アルゴリズムの handwritten と library:* を size ごとに横並びにし、speedup を出す。"""
    long = by_size(df, value=metric)
    pivot = (
        long.pivot_table(
            index=["algorithm", "size"], columns="implementation", values=metric, aggfunc="median"
        )
        .reset_index()
        .rename_axis(columns=None)
    )
    lib_cols = [c for c in pivot.columns if isinstance(c, str) and c.startswith("library")]
    if "handwritten" in pivot.columns and lib_cols:
        # speedup > 1 なら library が速い
        pivot["speedup"] = pivot["handwritten"] / pivot[lib_cols[0]]
    return pivot


def crossover_size(
    df: pd.DataFrame, *, metric: str = "elapsed_ms_median"
) -> dict[str, float | None]:
    """アルゴリズムごとに「library がはじめて handwritten より速くなる size」。無ければ None。"""
    table = handwritten_vs_library(df, metric=metric)
    out: dict[str, float | None] = {}
    if "speedup" not in table.columns:
        return out
    for algo, grp in table.sort_values("size").groupby("algorithm"):
        faster = grp[grp["speedup"] > 1.0]
        out[str(algo)] = float(faster["size"].iloc[0]) if not faster.empty else None
    return out
