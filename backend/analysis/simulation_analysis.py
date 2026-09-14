# DeciTima samples │ Phase 10
"""Simulation の分析(DataFrame → DataFrame の純粋関数)。

succeeded の simulate ジョブ(`jobs` テーブル、Phase 9-8/10-4)の JSONL を読み、
シナリオ横並びの比較表と感度分析の評価点を取り出す。`simulation_runs` のような専用
テーブルは持たない(進行のルール #17 ── 実消費者無しの新テーブルは見送り、Phase 9-8 の
`jobs` をそのまま読む。`load_benchmark_runs`(Phase 3)と対になる読み口)。

`analysis/` は app から切り離した dev トラック(pandas は dev 依存。app からは import しない。)
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from analysis.loaders import load_jobs


def load_simulation_jobs(path: str | Path) -> pd.DataFrame:
    """`load_jobs` の succeeded な simulate ジョブだけを「(job, scenario) 1 行」の flat
    DataFrame に展開する。base も scenario_label="base" として含める。列: job_id /
    created_at / problem_type / scenario_label / status / algorithm_name / error /
    metric.<key>...
    queued/running/failed のジョブ、solve ジョブ(result が base/scenarios を持たない)は
    行に含めない。
    """
    jobs = load_jobs(path)
    rows: list[dict] = []
    for _, job in jobs.iterrows():
        result = job["result"]
        if not result or "base" not in result or "scenarios" not in result:
            continue  # solve ジョブ、または未完了の simulate ジョブ
        for scenario in [{"label": "base", **result["base"]}, *result["scenarios"]]:
            row: dict = {
                "job_id": job["job_id"],
                "created_at": job["created_at"],
                "problem_type": job["problem_type"],
                "scenario_label": scenario["label"],
                "status": scenario["status"],
                "algorithm_name": scenario.get("algorithm_name"),
                "error": scenario.get("error"),
            }
            for k, v in (scenario.get("metrics") or {}).items():
                row[f"metric.{k}"] = v
            rows.append(row)
    return pd.DataFrame(rows)


def scenario_comparison(df: pd.DataFrame, job_id: str, *, metric: str) -> pd.DataFrame:
    """1 ジョブに絞って scenario_label × metric を並べた比較表(README の
    「車両数・配送時間・コスト」表と同じ形)。base を先頭に固定する。"""
    col = f"metric.{metric}"
    if col not in df.columns:
        raise KeyError(f"{col!r} 列が無い ── load_simulation_jobs の出力を渡す")
    out = df[df["job_id"] == job_id][["scenario_label", "status", col]].reset_index(drop=True)
    order = {"base": -1}  # base を常に先頭にする並び替えキー
    out = out.assign(_order=out["scenario_label"].map(lambda label: order.get(label, 0)))
    return (
        out.sort_values(["_order", "scenario_label"]).drop(columns="_order").reset_index(drop=True)
    )


def sensitivity_curve(path: str | Path, job_id: str) -> pd.DataFrame:
    """1 ジョブの sensitivity.evaluated(二分探索が実際に訪れた点)を param 昇順の
    DataFrame にする(tornado chart / 感度分析の可視化に使う)。sensitivity が無ければ空。
    """
    jobs = load_jobs(path)
    matched = jobs[jobs["job_id"] == job_id]
    empty = pd.DataFrame(columns=["param", "value"])
    if matched.empty:
        return empty
    result = matched.iloc[0]["result"] or {}
    sensitivity = result.get("sensitivity")
    if not sensitivity:
        return empty
    evaluated = sensitivity["evaluated"]
    return (
        pd.DataFrame({"param": [int(k) for k in evaluated], "value": list(evaluated.values())})
        .sort_values("param")
        .reset_index(drop=True)
    )
