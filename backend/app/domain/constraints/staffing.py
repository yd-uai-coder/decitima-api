"""staffing 制約のチェッカー ── 各スロットの割当人数が required_headcount ちょうどか。

StaffingConstraint は「スロットごとの必要人数を hard で守れ」という宣言的フラグ
(必要人数の数値自体は ShiftData 側が持つ。)。この制約を宣言した問題
だけがこのチェッカーで人数検証される
"""

from __future__ import annotations

from app.domain.problems.problem import OptimizationProblem, StaffingConstraint
from app.domain.problems.shift_scheduler import ShiftData
from app.domain.solutions.shift_scheduler import ShiftSolution
from app.domain.solutions.solution import CandidateSolution, ConstraintViolation


def check_staffing(
    constraint: StaffingConstraint,
    problem: OptimizationProblem,
    solution: CandidateSolution,
) -> ConstraintViolation | None:
    """人数が過不足なスロットが1つでもあれば違反を1件にまとめて返す。"""
    if not isinstance(problem.data, ShiftData) or not isinstance(
        solution.assignments, ShiftSolution
    ):
        return None
    assigned = solution.assignments.assignments
    off: list[dict[str, object]] = []
    for slot in problem.data.slots:
        count = len(set(assigned.get(slot.id, [])))
        if count != slot.required_headcount:
            off.append({"slot": slot.id, "assigned": count, "required": slot.required_headcount})
    if not off:
        return None
    return ConstraintViolation(
        constraint_kind=constraint.kind,
        severity=constraint.severity,
        message=f"{len(off)} slot(s) not staffed to required headcount",
        detail={"slots": off},
    )
