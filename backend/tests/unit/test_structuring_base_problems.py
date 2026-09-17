# DeciTima samples │ Phase 11
"""作業単位 11-2: ベース問題(`app.domain.problems.base_problems`)。

テスト対象 / ドライバ / スタブ:
- 対象: `get_base_problem` / `BASE_PROBLEMS`(純粋)
- ドライバ: このテスト関数(既存 `ProblemValidationService` を組み合わせて回帰確認する)
- スタブ不要 ── 対象・依存とも純粋(DB/Redis/LLM を一切呼ばない)
"""

from __future__ import annotations

import pytest

from app.domain.problems.base_problems import BASE_PROBLEMS, get_base_problem
from app.services.validation import ProblemValidationService


def test_base_problems_cover_all_six_problem_types() -> None:
    assert set(BASE_PROBLEMS) == {
        "route_planning",
        "network_design",
        "shift_scheduling",
        "travel_planning",
        "project_scheduling",
        "logistics_planning",
    }


@pytest.mark.parametrize("problem_type", list(BASE_PROBLEMS))
def test_get_base_problem_matches_requested_problem_type(problem_type: str) -> None:
    problem = get_base_problem(problem_type)
    assert problem.problem_type == problem_type
    assert problem.data.problem_type == problem_type


@pytest.mark.parametrize("problem_type", list(BASE_PROBLEMS))
def test_base_problems_pass_existing_validation(problem_type: str) -> None:
    """既存 Phase 0〜9 の Semantic Validation をそのまま通ることを確認する回帰テスト。"""
    ProblemValidationService().validate(get_base_problem(problem_type))


def test_get_base_problem_returns_independent_deep_copies() -> None:
    """呼び出しごとに独立したコピーを返す ── 1 件を書き換えても元・他の呼び出しに影響しない。"""
    first = get_base_problem("route_planning")
    second = get_base_problem("route_planning")
    assert first is not second
    assert first.data is not second.data

    first.objectives.append(first.objectives[0])
    assert len(second.objectives) == 1
    assert len(BASE_PROBLEMS["route_planning"].objectives) == 1
