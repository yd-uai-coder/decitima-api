"""制約。Constraint のサブタイプ（hard / soft）と、kind ごとのチェッカー関数を置く。
Verification がここへディスパッチする。実装は Phase 2。設計は textbook/Phase-0/Phase-0-6.md。
"""

from __future__ import annotations

from collections.abc import Callable

from app.domain.constraints.forbidden import check_forbidden
from app.domain.constraints.numeric_bound import check_numeric_bound
from app.domain.constraints.required_inclusion import check_required_inclusion
from app.domain.constraints.staffing import check_staffing
from app.domain.solutions.solution import ConstraintViolation


type ConstraintChecker = Callable[..., ConstraintViolation | None]

# kind -> チェッカー。verification.py はこの dict だけを見る
CHECKERS: dict[str, ConstraintChecker] = {
    "forbidden": check_forbidden,
    "required_inclusion": check_required_inclusion,
    "numeric_bound": check_numeric_bound,
    "staffing": check_staffing,
}

__all__ = [
    "CHECKERS",
    "ConstraintChecker",
    "check_forbidden",
    "check_numeric_bound",
    "check_required_inclusion",
    "check_staffing",
]
