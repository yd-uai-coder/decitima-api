""" 作業単位 1-6(補助): ProblemValidationService(route 限定の最小実装)。
    作業単位 2-2: ProblemValidationService(route + shift の Semantic Validation)。
"""

import pytest
from tests.fixtures.optimization import build_route_problem # (2-2テストで失効)：build_shift_problem

from app.domain.problems.problem import Objective, OptimizationProblem
from app.domain.problems.route_planner import RouteData, RouteEdge, RouteNode
from app.services.errors import InfeasibleProblemError, ProblemValidationError
from app.services.validation import ProblemValidationService

_SERVICE = ProblemValidationService()


def test_valid_route_problem_passes() -> None:
    # エラーが出なければ OK
    _SERVICE.validate(build_route_problem(forbidden=["e_bd"], required=["C"]))


# ------------------------------
# 以下はエラーが出ればOK
# ------------------------------
def test_unknown_start_node_is_rejected() -> None:
    problem = OptimizationProblem(
        problem_type="route_planning",
        objectives=[Objective(sense="minimize", target="total_weight")],
        data=RouteData(
            nodes=[RouteNode(id="A"), RouteNode(id="B")],
            edges=[RouteEdge(id="e_ab", source="A", target="B", weight=1)],
            start="Z",
            goal="B",
        ),
    )
    with pytest.raises(ProblemValidationError):
        _SERVICE.validate(problem)


def test_edge_referencing_unknown_node_is_rejected() -> None:
    problem = OptimizationProblem(
        problem_type="route_planning",
        objectives=[Objective(sense="minimize", target="total_weight")],
        data=RouteData(
            nodes=[RouteNode(id="A"), RouteNode(id="B")],
            edges=[RouteEdge(id="e_ax", source="A", target="X", weight=1)],
            start="A",
            goal="B",
        ),
    )
    with pytest.raises(ProblemValidationError):
        _SERVICE.validate(problem)


def test_unreachable_goal_is_infeasible() -> None:
    with pytest.raises(InfeasibleProblemError):
        _SERVICE.validate(build_route_problem(forbidden=["e_ce", "e_de"]))

# 作業単位:1-6で検証 ---Phase進行によりservice内の関数を差し替えた（分離・移植した）ため失効
# def test_shift_problem_passes_through_for_now() -> None:
#     # Phase 1 では shift の semantic validation は未実装 → 素通し(グレーは通す)
#     _SERVICE.validate(build_shift_problem())
