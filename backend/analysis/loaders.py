"""エクスポート済み JSONL を pandas DataFrame にする(file → DataFrame の純粋関数)。"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd


def _read_jsonl(path: str | Path) -> list[dict]:
    with Path(path).open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _payload(rec: dict) -> dict:
    # JSONB は dict のまま来るが、方言によっては str のこともある
    payload = rec["payload"]
    return json.loads(payload) if isinstance(payload, str) else payload


def load_benchmark_runs(path: str | Path) -> pd.DataFrame:
    """benchmark_runs の JSONL を「(run, algorithm) 1 行」の flat DataFrame にする。

    列: benchmark_id / created_at / problem_type / runs / algorithm / implementation /
        solution_status / elapsed_ms_median / elapsed_ms_p25 / elapsed_ms_p75 /
        peak_memory_kb / operation_count / hard_violations / soft_violations /
        quality_ratio / metrics.<key>...
    エントリが 1 つも無い run は落とす。行が無ければ空 DataFrame。
    """
    frames: list[pd.DataFrame] = []
    for rec in _read_jsonl(path):
        payload = _payload(rec)
        entries = payload.get("entries") or []
        if not entries:
            continue
        df = pd.json_normalize(entries).rename(
            columns={"algorithm.name": "algorithm", "algorithm.implementation": "implementation"}
        )
        df["benchmark_id"] = rec["id"]
        df["created_at"] = pd.to_datetime(rec["created_at"])
        df["problem_type"] = rec["problem_type"]
        df["runs"] = payload.get("runs")
        frames.append(df)
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def load_solutions(path: str | Path) -> pd.DataFrame:
    """solutions の JSONL を DataFrame にする(Phase 13 の布石)。

    列: solution_id / problem_id / created_at / status / algorithm_name /
        algorithm_implementation / metric_<key>...
    """
    rows: list[dict] = []
    for rec in _read_jsonl(path):
        payload = _payload(rec)
        row: dict = {
            "solution_id": rec["id"],
            "problem_id": rec["problem_id"],
            "created_at": rec["created_at"],
            "status": rec["status"],
            "algorithm_name": rec["algorithm_name"],
            "algorithm_implementation": rec["algorithm_implementation"],
        }
        for k, v in (payload.get("metrics") or {}).items():
            row[f"metric_{k}"] = v
        rows.append(row)
    df = pd.DataFrame(rows)
    if not df.empty:
        df["created_at"] = pd.to_datetime(df["created_at"])
    return df
