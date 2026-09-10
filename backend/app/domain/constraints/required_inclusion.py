"""required_inclusion 制約のチェッカー ── 解が「必ず含めるべき要素」をすべて含むか。
  - route 解   … 必須「経由ノード」id(path_node_ids に含まれるか)
  - network 解 … 必須「リンク」id(selected_link_ids に含まれるか)
  - travel 解  … 必須「訪問地」id(selected_place_ids に含まれるか)
"""

from __future__ import annotations

from app.domain.problems.problem import OptimizationProblem, RequiredInclusionConstraint
from app.domain.solutions.solution import CandidateSolution, ConstraintViolation
from app.domain.constraints.elements import solution_element_ids


def check_required_inclusion(
    constraint: RequiredInclusionConstraint,
    problem: OptimizationProblem,
    solution: CandidateSolution,
) -> ConstraintViolation | None:
    """解が必須要素(必須経由ノード id 等)を取りこぼしていれば違反を1件返す。"""
    present = solution_element_ids(solution, aspect="nodes")
    if present is None:
        return None
    missing = sorted(set(constraint.items) - present)
    if not missing:
        return None
    return ConstraintViolation(
        constraint_kind=constraint.kind,
        severity=constraint.severity,
        message=f"path misses required node(s): {sorted(missing)}",
        detail={"missing": sorted(missing)},
    )
