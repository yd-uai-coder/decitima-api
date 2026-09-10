# DeciTima samples │ Phase 7
"""作業単位 7-3: travel_planning problem_type の配線(schema union / semantic / structure)。

テスト対象 / ドライバ / スタブ:
- 対象: `TravelData` / `TravelSolution`(判別可能ユニオン)、`SEMANTIC_CHECKS["travel_planning"]`、
  `verify_travel_structure`、`ProblemValidationService.validate`、`structural_verify` のディスパッチ
- ドライバ: このテスト関数 / fixture
- スタブ: 不要 ── すべて純粋な値オブジェクト / 純粋関数。`ProblemValidationService` は DB を持たない
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from tests.fixtures.optimization import build_travel_problem, build_travel_solution

from app.domain.problems.problem import OptimizationProblem
from app.domain.problems.travel_planner import TravelData
from app.domain.solutions.solution import CandidateSolution
from app.domain.solutions.structure import structural_verify, verify_travel_structure
from app.domain.solutions.travel_planner import TravelSolution
from app.services.errors import InfeasibleProblemError, ProblemValidationError
from app.services.validation import ProblemValidationService

_VALIDATION = ProblemValidationService()


# --- 判別可能ユニオン ------------------------------------------------------


def test_problem_data_narrows_to_travel_data() -> None:
    problem = build_travel_problem()
    assert isinstance(problem.data, TravelData)
    assert problem.problem_type == "travel_planning"


def test_solution_data_narrows_to_travel_solution() -> None:
    sol = build_travel_solution(["P1"], ["P1"])
    assert isinstance(sol.assignments, TravelSolution)


def test_problem_type_must_match_data() -> None:
    with pytest.raises(ValidationError):
        OptimizationProblem(
            problem_type="route_planning",  # data は travel
            objectives=[],
            data=build_travel_problem().data,
        )


def test_travel_data_rejects_unknown_leg_endpoint() -> None:
    base = build_travel_problem().data
    assert isinstance(base, TravelData)
    with pytest.raises(ValidationError, match="unknown place"):
        TravelData(
            places=base.places,
            legs=[{"id": "bad", "endpoints": ("P0", "ZZZ"), "travel_cost": 1, "travel_time": 1}],  # type: ignore[list-item]
            budget=10,
            time_budget=10,
        )


# --- Semantic Validation -------------------------------------------------


def test_valid_travel_problem_passes_validation() -> None:
    _VALIDATION.validate(build_travel_problem())  # 例外が出なければ OK


def test_no_places_is_integrity_error() -> None:
    problem = build_travel_problem()
    empty = problem.model_copy(
        update={"data": problem.data.model_copy(update={"places": [], "legs": []})}
    )
    with pytest.raises(ProblemValidationError):
        _VALIDATION.validate(empty)


def test_all_places_too_expensive_is_infeasible() -> None:
    """一番安い place ですら予算を超えるなら InfeasibleProblemError(何も訪れられない)。"""
    problem = build_travel_problem(budget=5)
    assert isinstance(problem.data, TravelData)
    pricey = [p.model_copy(update={"cost": 999}) for p in problem.data.places]
    data = problem.data.model_copy(update={"places": pricey})
    with pytest.raises(InfeasibleProblemError):
        _VALIDATION.validate(problem.model_copy(update={"data": data}))


def test_all_places_too_long_is_infeasible() -> None:
    """一番短い滞在時間ですら time_budget を超えるなら InfeasibleProblemError。"""
    problem = build_travel_problem(time_budget=5)
    assert isinstance(problem.data, TravelData)
    slow = [p.model_copy(update={"duration": 999}) for p in problem.data.places]
    data = problem.data.model_copy(update={"places": slow})
    with pytest.raises(InfeasibleProblemError):
        _VALIDATION.validate(problem.model_copy(update={"data": data}))


# --- 構造検証 -------------------------------------------------------------


def test_verify_travel_structure_accepts_consistent_plan() -> None:
    data = build_travel_problem().data
    sol = build_travel_solution(
        ["P1", "P2"], ["P1", "P2"], total_value=18, total_cost=5, total_time=5
    )
    assert verify_travel_structure(data, sol.assignments) == []  # type: ignore[arg-type]


def test_verify_travel_structure_flags_unknown_place() -> None:
    data = build_travel_problem().data
    sol = build_travel_solution(["ZZZ"], ["ZZZ"])
    violations = verify_travel_structure(data, sol.assignments)  # type: ignore[arg-type]
    assert any("unknown place" in v.message for v in violations)


def test_verify_travel_structure_flags_order_mismatch() -> None:
    data = build_travel_problem().data
    sol = build_travel_solution(["P1", "P2"], ["P1"])  # order != selected
    violations = verify_travel_structure(data, sol.assignments)  # type: ignore[arg-type]
    assert any("permutation" in v.message for v in violations)


def test_verify_travel_structure_flags_budget_overrun() -> None:
    data = build_travel_problem(budget=3).data
    sol = build_travel_solution(["P1"], ["P1"], total_value=10, total_cost=50, total_time=2)
    violations = verify_travel_structure(data, sol.assignments)  # type: ignore[arg-type]
    assert any("budget" in v.message for v in violations)


def test_structural_verify_dispatches_travel() -> None:
    problem = build_travel_problem()
    sol: CandidateSolution = build_travel_solution(
        ["P1"], ["P1"], total_value=10, total_cost=4, total_time=3
    )
    violations, metrics = structural_verify(problem, sol)
    assert metrics == {}
    assert isinstance(violations, list)
