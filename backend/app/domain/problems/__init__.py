"""問題定義パッケージ。
分割したファイルの内訳を利用側に見せないための「公開窓口」。
利用側は `from app.domain.problems import OptimizationProblem, RouteData` と書け、
あとでファイルを分割・統合しても import 文が変わらない。

ユニオン(ProblemData)を __init__.py に置くと problem.py <-> __init__.py が循環するので、
ユニオンの定義は problem.py に置き、ここは re-export だけにする。
ruff F401 対策で __all__ を付ける(既存 app/models/__init__.py と同じ)。
"""

from app.domain.problems.problem import (
    AnyConstraint, ConstraintBase, ForbiddenConstraint, GenericConstraint, NumericBoundConstraint,
    Objective, OptimizationProblem, ProblemData,
    RequiredInclusionConstraint, StaffingConstraint,
)
from app.domain.problems.route_planner import RouteData, RouteEdge, RouteNode
from app.domain.problems.shift_scheduler import ShiftData, ShiftSlot, Staff
from app.domain.problems.network_design import NetworkNode, NetworkLink, NetworkDesignData
from app.domain.problems.travel_planner import Place, TravelData, TravelLeg  # (Phase 7-3)
from app.domain.problems.project_manager import ProjectTask,TaskDependency, ProjectData

__all__ = [
    "AnyConstraint",
    "ConstraintBase",
    "ForbiddenConstraint",
    "GenericConstraint",
    "NumericBoundConstraint",
    "Objective",
    "OptimizationProblem",
    "ProblemData",
    "RequiredInclusionConstraint",
    "RouteData",
    "RouteEdge",
    "RouteNode",
    "ShiftData",
    "ShiftSlot",
    "Staff",
    "StaffingConstraint",
    "NetworkNode",
    "NetworkLink",
    "NetworkDesignData",
    "Place",
    "TravelData",
    "TravelLeg",
    "ProjectTask",
    "TaskDependency",
    "ProjectData",
]