"""作業単位 1-1: 共通スキーマ。純粋関数テスト(DB 不要)。"""

import pytest
from pydantic import ValidationError
from tests.fixtures.optimization import build_route_problem, build_shift_problem

from app.domain.problems.problem import (
    ForbiddenConstraint,
    GenericConstraint,
    OptimizationProblem,
)
from app.domain.problems.route_planner import RouteData
from app.domain.solutions.route_planner import RouteSolution
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution


def test_route_problem_builds_and_narrows() -> None:
    problem = build_route_problem(forbidden=["e_bd"], required=["C"])
    assert problem.problem_type == "route_planning"
    assert isinstance(problem.data, RouteData)
    assert problem.data.problem_type == "route_planning"


def test_shift_problem_roundtrips_through_json() -> None:
    problem = build_shift_problem()
    restored = OptimizationProblem.model_validate(problem.model_dump(mode="json"))
    assert restored == problem


def test_constraint_union_picks_subtype_by_kind() -> None:
    problem = OptimizationProblem.model_validate(
        {
            "problem_type": "route_planning",
            "objectives": [{"sense": "minimize", "target": "total_weight"}],
            "constraints": [
                {"kind": "forbidden", "severity": "hard", "items": ["e_bd"]},
                {"kind": "respect_days_off", "severity": "soft", "penalty": 5.0},
            ],
            "data": {
                "problem_type": "route_planning",
                "nodes": [{"id": "A"}, {"id": "B"}],
                "edges": [{"id": "e_ab", "source": "A", "target": "B", "weight": 1}],
                "start": "A",
                "goal": "B",
            },
        }
    )
    # 既知 kind は専用サブタイプ、未知 kind は GenericConstraint にフォールバック
    assert isinstance(problem.constraints[0], ForbiddenConstraint)
    assert isinstance(problem.constraints[1], GenericConstraint)


def test_negative_edge_weight_is_rejected() -> None:
    with pytest.raises(ValidationError):
        RouteData.model_validate(
            {
                "nodes": [{"id": "A"}, {"id": "B"}],
                "edges": [{"id": "e", "source": "A", "target": "B", "weight": -1}],
                "start": "A",
                "goal": "B",
            }
        )


def test_problem_type_must_match_data() -> None:
    with pytest.raises(ValidationError):
        OptimizationProblem.model_validate(
            {
                "problem_type": "shift_scheduling",
                "objectives": [],
                "data": {
                    "problem_type": "route_planning",
                    "nodes": [],
                    "edges": [],
                    "start": "A",
                    "goal": "B",
                },
            }
        )


def test_candidate_solution_requires_produced_by() -> None:
    with pytest.raises(ValidationError):
        CandidateSolution.model_validate(
            {
                "status": "valid",
                "assignments": {
                    "problem_type": "route_planning",
                    "path_node_ids": ["A"],
                    "path_edge_ids": [],
                    "total_weight": 0.0,
                },
            }
        )


def test_candidate_solution_ok() -> None:
    sol = CandidateSolution(
        status="valid",
        assignments=RouteSolution(
            path_node_ids=["A", "B"], path_edge_ids=["e_ab"], total_weight=1.0
        ),
        metrics={"total_weight": 1.0},
        produced_by=AlgorithmMeta(name="dijkstra", family="graph", implementation="handwritten"),
    )
    assert isinstance(sol.assignments, RouteSolution)
