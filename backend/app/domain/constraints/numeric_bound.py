"""numeric_bound 制約のチェッカー ── 解のメトリクスが上限・下限・等値を守っているか。

`solution.metrics[constraint.field]` を `constraint.operator constraint.value` と比較する。
route の `total_weight`、shift の `labor_cost` など、Verification が確定したメトリクスに対して
効く(SolutionVerificationService が構造検証で metrics を埋めた「後」に呼ばれる)。
"""

from __future__ import annotations

from collections.abc import Callable
from operator import eq, ge, gt, le, lt

from app.domain.problems.problem import NumericBoundConstraint, OptimizationProblem
from app.domain.solutions.solution import CandidateSolution, ConstraintViolation

# 比較演算子の文字列 → 関数。NumericBoundConstraint.operator が取りうる 5 種
_OPS: dict[str, Callable[[float, float], bool]] = {
    "<=": le,
    ">=": ge,
    "==": eq,
    "<": lt,
    ">": gt,
}


def check_numeric_bound(
    constraint: NumericBoundConstraint,
    problem: OptimizationProblem,
    solution: CandidateSolution,
) -> ConstraintViolation | None:
    """metrics[field] が境界を満たさなければ違反を1件返す。metrics に無ければ素通し。"""
    actual = solution.metrics.get(constraint.field)
    if actual is None:
        # そのメトリクスを誰も計算していない → 検証できないので違反にしない
        # (未対応 kind を素通しするのと同じ方針。Phase-0-6.md §3.2)
        return None
    if _OPS[constraint.operator](actual, constraint.value):
        return None
    return ConstraintViolation(
        constraint_kind=constraint.kind,
        severity=constraint.severity,
        message=(f"{constraint.field}={actual} violates {constraint.operator} {constraint.value}"),
        detail={
            "field": constraint.field,
            "actual": actual,
            "operator": constraint.operator,
            "expected": constraint.value,
        },
    )
