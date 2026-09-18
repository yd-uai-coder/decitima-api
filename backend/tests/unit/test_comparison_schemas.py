# DeciTima samples │ 初出 Phase 14
"""作業単位 14-5: `app/schemas/comparison.py` の型定義の確認(純粋、スタブ不要)。

対象が純粋(副作用なし・外部依存を呼ばない)なので、SUT を素の pytest で直接検証するだけで
足りる(進行のルール #14)。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from tests.fixtures.optimization import build_route_problem

from app.schemas.comparison import ComparisonMetrics, ComparisonRequest, RunOutcome


def test_comparison_request_defaults() -> None:
    request = ComparisonRequest(problem=build_route_problem())
    assert request.llm_runs == 5
    assert request.algorithm is None


def test_comparison_request_llm_runs_bounds() -> None:
    with pytest.raises(ValidationError):
        ComparisonRequest(problem=build_route_problem(), llm_runs=0)
    with pytest.raises(ValidationError):
        ComparisonRequest(problem=build_route_problem(), llm_runs=21)


def test_run_outcome_defaults_represent_a_failed_run() -> None:
    outcome = RunOutcome(error="boom")
    assert outcome.status is None
    assert outcome.metrics == {}
    assert outcome.hard_violations == 0


def test_comparison_metrics_allows_none_optimality() -> None:
    """目的が無い / 比較不能なケースでは optimality を None にできる。"""
    metrics = ComparisonMetrics(
        constraint_compliance_rate_algorithm=1.0,
        constraint_compliance_rate_llm=0.0,
        optimality_avg_quality_ratio_llm=None,
        reproducibility_distinct_solutions_llm=0,
        execution_time_ms_algorithm=1.0,
        execution_time_ms_llm_median=1.0,
        error_rate_llm=1.0,
    )
    assert metrics.optimality_avg_quality_ratio_llm is None
