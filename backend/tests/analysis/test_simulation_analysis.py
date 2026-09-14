# DeciTima samples │ Phase 10
"""作業単位 10-5: analysis/simulation_analysis.py(分析トラック)。

対象 = ファイル → DataFrame / DataFrame → DataFrame の純粋関数。ドライバ = このテスト関数
(pytest の tmp_path に fake な jobs JSONL を書く)。スタブ不要(`analysis/` は app から
切り離した純粋レイヤー ── `Phase-3-8.md`)。
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from analysis.simulation_analysis import (
    load_simulation_jobs,
    scenario_comparison,
    sensitivity_curve,
)


def _write_jobs_jsonl(path: Path, records: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in records) + "\n")


def _succeeded_simulate_record(job_id: str) -> dict:
    return {
        "id": job_id,
        "user_id": "u1",
        "problem_type": "project_scheduling",
        "status": "succeeded",
        "created_at": "2026-09-13T00:00:00+00:00",
        "updated_at": "2026-09-13T00:00:05+00:00",
        "payload": {
            "request": {"problem": {}, "scenarios": []},
            "result": {
                "base": {
                    "label": "base",
                    "status": "valid",
                    "metrics": {"makespan": 10.0},
                    "algorithm_name": "priority_list",
                },
                "scenarios": [
                    {
                        "label": "tighter",
                        "status": "valid",
                        "metrics": {"makespan": 14.0},
                        "algorithm_name": "priority_list",
                    },
                    {
                        "label": "broken",
                        "status": "invalid_scenario",
                        "metrics": {},
                        "error": "boom",
                    },
                ],
                "sensitivity": {
                    "threshold_value": 4,
                    "evaluated": {"3": 14.0, "5": 11.0, "4": 12.0},
                },
            },
            "error": None,
        },
    }


def test_load_simulation_jobs_expands_base_and_scenarios_into_rows(tmp_path: Path) -> None:
    jsonl = tmp_path / "jobs.jsonl"
    _write_jobs_jsonl(jsonl, [_succeeded_simulate_record("job-1")])

    df = load_simulation_jobs(jsonl)

    assert set(df["scenario_label"]) == {"base", "tighter", "broken"}
    base_row = df[df["scenario_label"] == "base"].iloc[0]
    assert base_row["metric.makespan"] == 10.0
    broken = df[df["scenario_label"] == "broken"].iloc[0]
    assert broken["status"] == "invalid_scenario"
    assert broken["error"] == "boom"


def test_load_simulation_jobs_skips_solve_jobs_and_unfinished_jobs(tmp_path: Path) -> None:
    jsonl = tmp_path / "jobs.jsonl"
    _write_jobs_jsonl(
        jsonl,
        [
            {
                "id": "solve-1",
                "user_id": "u1",
                "problem_type": "route_planning",
                "status": "succeeded",
                "created_at": "2026-09-13T00:00:00+00:00",
                "updated_at": "2026-09-13T00:00:00+00:00",
                "payload": {"request": {}, "result": {"status": "valid"}, "error": None},
            },
            {
                "id": "sim-queued",
                "user_id": "u1",
                "problem_type": "project_scheduling",
                "status": "queued",
                "created_at": "2026-09-13T00:00:00+00:00",
                "updated_at": "2026-09-13T00:00:00+00:00",
                "payload": {"request": {}, "result": None, "error": None},
            },
        ],
    )
    df = load_simulation_jobs(jsonl)
    assert df.empty


def test_scenario_comparison_orders_base_first() -> None:
    df = pd.DataFrame(
        [
            {
                "job_id": "j1",
                "scenario_label": "tighter",
                "status": "valid",
                "metric.makespan": 14.0,
            },
            {"job_id": "j1", "scenario_label": "base", "status": "valid", "metric.makespan": 10.0},
        ]
    )
    out = scenario_comparison(df, "j1", metric="makespan")
    assert list(out["scenario_label"]) == ["base", "tighter"]


def test_sensitivity_curve_sorts_evaluated_points_by_param(tmp_path: Path) -> None:
    jsonl = tmp_path / "jobs.jsonl"
    _write_jobs_jsonl(jsonl, [_succeeded_simulate_record("job-1")])

    curve = sensitivity_curve(jsonl, "job-1")

    assert list(curve["param"]) == [3, 4, 5]
    assert list(curve["value"]) == [14.0, 12.0, 11.0]


def test_sensitivity_curve_is_empty_when_no_sensitivity_requested(tmp_path: Path) -> None:
    record = _succeeded_simulate_record("job-2")
    record["payload"]["result"]["sensitivity"] = None
    jsonl = tmp_path / "jobs.jsonl"
    _write_jobs_jsonl(jsonl, [record])

    assert sensitivity_curve(jsonl, "job-2").empty
