"""作業単位 2-3: 制約 kind ごとのチェッカー(app/domain/constraints/)。

各チェッカーは純粋関数。スタブ不要 ── 問題と解を手で組んで直接呼ぶ。
"""

from tests.fixtures.optimization import (
    build_route_problem,
    build_shift_problem,
    build_shift_solution,
)

from app.domain.constraints import CHECKERS
from app.domain.constraints.forbidden import check_forbidden
from app.domain.constraints.numeric_bound import check_numeric_bound
from app.domain.constraints.required_inclusion import check_required_inclusion
from app.domain.constraints.staffing import check_staffing
from app.domain.problems.problem import (
    ForbiddenConstraint,
    NumericBoundConstraint,
    RequiredInclusionConstraint,
    StaffingConstraint,
)
from app.domain.solutions.route_planner import RouteSolution
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution

_META = AlgorithmMeta(name="x", family="graph", implementation="handwritten")


def _route_solution(*, weight: float = 9.0) -> CandidateSolution:
    return CandidateSolution(
        status="valid",
        assignments=RouteSolution(
            path_node_ids=["A", "B", "C", "E"],
            path_edge_ids=["e_ab", "e_bc", "e_ce"],
            total_weight=weight,
        ),
        metrics={"total_weight": weight},
        produced_by=_META,
    )


def test_registry_has_all_mvp_kinds() -> None:
    assert set(CHECKERS) == {"forbidden", "required_inclusion", "numeric_bound", "staffing"}


_ROUTE_PROBLEM = build_route_problem()


def test_numeric_bound_satisfied_returns_none() -> None:
    c = NumericBoundConstraint(severity="hard", field="total_weight", operator="<=", value=10)
    assert check_numeric_bound(c, _ROUTE_PROBLEM, _route_solution(weight=9.0)) is None


def test_numeric_bound_violated_returns_violation() -> None:
    c = NumericBoundConstraint(severity="hard", field="total_weight", operator="<=", value=8)
    v = check_numeric_bound(c, _ROUTE_PROBLEM, _route_solution(weight=9.0))
    assert v is not None and v.severity == "hard"


def test_numeric_bound_missing_metric_is_skipped() -> None:
    c = NumericBoundConstraint(severity="hard", field="labor_cost", operator="<=", value=1)
    assert check_numeric_bound(c, _ROUTE_PROBLEM, _route_solution()) is None


def test_forbidden_on_non_route_solution_is_skipped() -> None:
    c = ForbiddenConstraint(severity="hard", items=["e_bd"])
    shift_sol = build_shift_solution({"s1": ["tanaka"]})
    assert check_forbidden(c, build_shift_problem(), shift_sol) is None


def test_required_inclusion_missing_node_returns_violation() -> None:
    c = RequiredInclusionConstraint(severity="hard", items=["D"])
    v = check_required_inclusion(c, _ROUTE_PROBLEM, _route_solution())
    assert v is not None and v.detail["missing"] == ["D"]


def test_staffing_exact_headcount_returns_none() -> None:
    problem = build_shift_problem()
    sol = build_shift_solution({"s1": ["tanaka"], "s2": ["sato"], "s3": ["ito"], "s4": ["sato"]})
    assert check_staffing(StaffingConstraint(severity="hard"), problem, sol) is None


def test_staffing_understaffed_returns_violation() -> None:
    problem = build_shift_problem()
    sol = build_shift_solution({"s1": ["tanaka"], "s2": [], "s3": ["ito"], "s4": ["sato"]})
    v = check_staffing(StaffingConstraint(severity="hard"), problem, sol)
    assert v is not None and v.detail["slots"][0]["slot"] == "s2"
