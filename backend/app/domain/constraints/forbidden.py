"""forbidden 制約のチェッカー ── 解に「使ってはいけない要素」が含まれていないか。
  - route 解   … 使ったエッジ id
  - network 解 … 選択したリンク id
  - travel 解  … 訪れた place id
"""

from __future__ import annotations

from app.domain.problems.problem import ForbiddenConstraint, OptimizationProblem
from app.domain.solutions.solution import CandidateSolution, ConstraintViolation
from app.domain.constraints.elements import solution_element_ids


def check_forbidden(
    constraint: ForbiddenConstraint,
    problem: OptimizationProblem,
    solution: CandidateSolution,
) -> ConstraintViolation | None:
    """解が禁止要素(禁止エッジ id 等)を含んでいれば違反を1件返す。"""
    used = solution_element_ids(solution, aspect="edges")
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
