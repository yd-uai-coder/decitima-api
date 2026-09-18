"""CI 回帰検知 ── `analysis/benchmark_report.py::regression()`

代表的な (problem, strategy) の組を `measure_call`(Phase 3)で実測し、`benchmark_runs` と
同じ形の JSONL を組み立てて、コミット済みのベースライン(`analysis/data/ci_baseline_
benchmark_runs.jsonl`)と `regression()` で突き合わせる。比率(ratio)が閾値を超えた
アルゴリズムがあれば非ゼロ終了(GitHub Actions のジョブを失敗させる)。

閾値は 3.0(3倍)── CI ランナーの実行環境ノイズを吸収しつつ、O(n)→O(n^2) のような
明確な計算量の劣化は検知できる大きさに設定した(既存の `measure_call` は中央値を使うため
単発の外れ値には強いが、ランナー間の絶対性能差は大きいので緩めに取る)。

`uv run python -m scripts.ci_regression_check` で実行する(`app/` から import されない、
`analysis` グループの依存が要る ── `uv sync --group analysis`)。

`analysis.benchmark_report`/`analysis.loaders`(pandas 依存)の import は
`main()` 内のローカル import にする ── モジュール先頭に置くと、pandas 未導入の環境で
`tests/unit/test_ci_regression_check.py`(このモジュールを import するだけの単体テスト、
pandas を使わない `_measure_one`/`_TARGETS` だけを見る)まで collection エラーになり、
「analysis 依存群が無くても bare pytest は通る」という Phase 15-1 の方針が崩れる
(`tests/analysis/` 配下は `analysis` マーカーで守れるが、このテストは tests/unit/ にあり
マーカーの対象外のため)。
"""

from __future__ import annotations

import json
import sys
import uuid
from datetime import UTC, datetime
from pathlib import Path

from app.algorithms.graph.dijkstra import DijkstraStrategy
from app.algorithms.optimization.knapsack import KnapsackDpTravelStrategy
from app.algorithms.scheduling.cpm import CpmScheduleStrategy
from app.services.measurement import measure_call

_BASELINE_PATH = (
    Path(__file__).resolve().parent.parent / "analysis/data/ci_baseline_benchmark_runs.jsonl"
)
_CURRENT_PATH = Path(__file__).resolve().parent.parent / "_ci_current_benchmark_runs.jsonl"
_REGRESSION_RATIO_THRESHOLD = 3.0

# 代表的な (problem, strategy) の組。3ドメイン・3アルゴリズムファミリーを横断させる
# (グラフ探索 / DP / スケジューリング)── 全アルゴリズムを網羅するのはこのスクリプトの
# 目的ではない(それは既存 BenchmarkService の役割)。CI での「明確な劣化」検知に絞る。
_TARGETS = [
    ("route_planning", DijkstraStrategy()),
    ("travel_planning", KnapsackDpTravelStrategy()),
    ("project_scheduling", CpmScheduleStrategy()),
]


def _measure_one(problem_type: str, strategy) -> dict:
    from tests.fixtures.optimization import (
        build_route_problem,
        build_scaled_project_problem,
        build_scaled_travel_problem,
    )

    problem = {
        "route_planning": lambda: build_route_problem(),
        "travel_planning": lambda: build_scaled_travel_problem(8, budget=30, time_budget=30),
        "project_scheduling": lambda: build_scaled_project_problem(50),
    }[problem_type]()

    _, measurement = measure_call(lambda: strategy.solve(problem), 3)
    return {
        "algorithm": {"name": strategy.meta.name, "implementation": strategy.meta.implementation},
        "solution_status": "n/a",
        "metrics": {},
        "elapsed_ms_median": measurement.elapsed_ms_median,
        "elapsed_ms_p25": measurement.elapsed_ms_p25,
        "elapsed_ms_p75": measurement.elapsed_ms_p75,
        "peak_memory_kb": measurement.peak_memory_kb,
        "operation_count": None,
    }


def main() -> int:
    from analysis.benchmark_report import regression
    from analysis.loaders import load_benchmark_runs

    entries = [_measure_one(pt, strategy) for pt, strategy in _TARGETS]
    record = {
        "id": str(uuid.uuid4()),
        "user_id": str(uuid.uuid4()),
        "problem_type": "ci",
        "created_at": datetime.now(UTC).isoformat(),
        "payload": {"entries": entries},
    }
    _CURRENT_PATH.write_text(json.dumps(record) + "\n", encoding="utf-8")

    baseline = load_benchmark_runs(_BASELINE_PATH)
    current = load_benchmark_runs(_CURRENT_PATH)
    diff = regression(baseline, current)

    regressed = diff[diff["ratio"] > _REGRESSION_RATIO_THRESHOLD]
    print(diff.to_string(index=False))
    if not regressed.empty:
        print(f"\n回帰検知: 閾値({_REGRESSION_RATIO_THRESHOLD}倍)を超えたアルゴリズムがあります")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
