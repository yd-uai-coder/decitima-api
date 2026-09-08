"""forbidden 制約のチェッカー ── 解に「使ってはいけない要素」が含まれていないか。"""

from __future__ import annotations

from app.domain.problems.problem import ForbiddenConstraint, OptimizationProblem
from app.domain.solutions.network_design import NetworkDesignSolution
from app.domain.solutions.route_planner import RouteSolution
from app.domain.solutions.solution import CandidateSolution, ConstraintViolation


def _used_element_ids(solution: CandidateSolution) -> set[str] | None:
    """解が「使った要素」の id 集合。forbidden / required_inclusion が対象にできない解型は None。"""
    assignments = solution.assignments
    if isinstance(assignments, RouteSolution):
        return set(assignments.path_edge_ids)
    if isinstance(assignments, NetworkDesignSolution):
        return set(assignments.selected_link_ids)
    return None


def check_forbidden(
    constraint: ForbiddenConstraint,
    problem: OptimizationProblem,
    solution: CandidateSolution,
) -> ConstraintViolation | None:
    """解が禁止要素(禁止エッジ id 等)を含んでいれば違反を1件返す。"""
    used = _used_element_ids(solution)
    if used is None:
        return None  # この解型には forbidden を適用しない(素通し)
    hit = used & set(constraint.items)
    if not hit:
        return None
    return ConstraintViolation(
        constraint_kind=constraint.kind,
        severity=constraint.severity,
        message=f"path uses forbidden edge(s): {sorted(hit)}",
        detail={"forbidden_hit": sorted(hit)},
    )
