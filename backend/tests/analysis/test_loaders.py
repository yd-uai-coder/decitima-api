# DeciTima samples │ Phase 3
"""作業単位 3-8: analysis.loaders。

対象 = `load_benchmark_runs` / `load_solutions`(file → DataFrame の純粋関数)。
ドライバ = このテスト関数。**スタブ不要** ── ファイルを読んで DataFrame を返すだけ。
"""

import json
from pathlib import Path

import pandas as pd

from analysis.loaders import load_benchmark_runs, load_solutions

_SAMPLE = Path(__file__).parents[2] / "analysis" / "data" / "sample_benchmark_runs.jsonl"


def _write_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


def _bench_record(bid: str, algos: list[str]) -> dict:
    return {
        "id": bid,
        "user_id": "u-1",
        "problem_type": "route_planning",
        "created_at": "2026-09-02T00:00:00+00:00",
        "payload": {
            "problem": {"problem_type": "route_planning"},
            "runs": 3,
            "entries": [
                {
                    "algorithm": {"name": a, "family": "graph", "implementation": "handwritten"},
                    "solution_status": "valid",
                    "metrics": {"total_weight": 5.0, "_ops": 4.0},
                    "elapsed_ms_median": 0.1,
                    "elapsed_ms_p25": 0.1,
                    "elapsed_ms_p75": 0.1,
                    "peak_memory_kb": 1.0,
                    "operation_count": 4,
                    "hard_violations": 0,
                    "soft_violations": 0,
                    "quality_ratio": 1.0,
                }
                for a in algos
            ],
        },
    }


def test_flattens_to_one_row_per_run_algorithm(tmp_path: Path) -> None:
    p = tmp_path / "b.jsonl"
    _write_jsonl(
        p,
        [_bench_record("b1", ["dijkstra", "brute_force"]), _bench_record("b2", ["dijkstra"])],
    )
    df = load_benchmark_runs(p)
    assert len(df) == 3  # 2 + 1
    expected_cols = {"benchmark_id", "algorithm", "implementation", "elapsed_ms_median", "runs"}
    assert expected_cols <= set(df.columns)
    assert set(df["algorithm"]) == {"dijkstra", "brute_force"}
    assert pd.api.types.is_datetime64_any_dtype(df["created_at"])


def test_empty_entries_are_skipped(tmp_path: Path) -> None:
    p = tmp_path / "b.jsonl"
    rec = _bench_record("b1", [])
    _write_jsonl(p, [rec])
    assert load_benchmark_runs(p).empty


def test_string_payload_is_parsed(tmp_path: Path) -> None:
    p = tmp_path / "b.jsonl"
    rec = _bench_record("b1", ["dijkstra"])
    rec["payload"] = json.dumps(rec["payload"])  # SQLite 方言などで str になるケース
    _write_jsonl(p, [rec])
    assert len(load_benchmark_runs(p)) == 1


def test_load_solutions_extracts_metrics(tmp_path: Path) -> None:
    p = tmp_path / "s.jsonl"
    _write_jsonl(
        p,
        [
            {
                "id": "s1",
                "problem_id": "p1",
                "created_at": "2026-09-02T00:00:00+00:00",
                "status": "valid",
                "algorithm_name": "dijkstra",
                "algorithm_implementation": "handwritten",
                "payload": {"status": "valid", "metrics": {"total_weight": 9.0, "_ops": 6.0}},
            }
        ],
    )
    df = load_solutions(p)
    assert list(df["solution_id"]) == ["s1"]
    assert df.loc[0, "metric_total_weight"] == 9.0


def test_committed_sample_loads() -> None:
    """analysis/data/sample_benchmark_runs.jsonl が壊れていないこと(notebook が依存する)。"""
    df = load_benchmark_runs(_SAMPLE)
    assert not df.empty
    assert "dijkstra" in set(df["algorithm"])
    assert "brute_force" in set(df["algorithm"])
