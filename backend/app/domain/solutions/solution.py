"""解の中核(アグリゲータ)。
- AlgorithmMeta / ConstraintViolation
- SolutionData(problem_type を判別子にした判別可能ユニオン)
- CandidateSolution
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any, Literal
from pydantic import BaseModel, Field
from app.domain.solutions.route_planner import RouteSolution
from app.domain.solutions.shift_scheduler import ShiftSolution
from app.domain.solutions.network_design import NetworkDesignSolution
from app.domain.solutions.travel_planner import TravelSolution
from app.domain.solutions.project_manager import ProjectSolution
from app.domain.solutions.logistics import LogisticsSolution

# ---------------------------------------------------------------------------
# 解候補（CandidateSolution）
# ---------------------------------------------------------------------------

# AlgorithmMeta.family は app/algorithms/ の 5 サブパッケージと 1 対 1
type AlgorithmFamily = Literal["search", "graph", "optimization", "scheduling", "patterns","llm"]

# 解の状態
type SolutionStatus = Literal["valid", "invalid", "infeasible"]


class ConstraintViolation(BaseModel):
    """検証で見つかった制約違反1件。どの制約を、どう破ったか。"""

    constraint_kind: str
    severity: Literal["hard", "soft"]
    message: str
    detail: dict[str, Any] = Field(default_factory=dict)


class AlgorithmMeta(BaseModel):
    """解を生成したアルゴリズムの素性。比較可能性（NFR-3）の土台になる。"""

    name: str
    family: AlgorithmFamily
    # implementation: "handwritten" / "library:networkx" / "library:ortools" など
    implementation: str
    time_complexity: str | None = None
    space_complexity: str | None = None


# problem_type 判別子付きの判別可能ユニオン。
# 新しい問題タイプはここに 1 項目足すだけ。
type SolutionData = Annotated[
    RouteSolution 
    | ShiftSolution 
    | NetworkDesignSolution 
    | TravelSolution 
    | ProjectSolution
    | LogisticsSolution,
    Field(discriminator="problem_type"),
]


class CandidateSolution(BaseModel):
    """アルゴリズムが返す候補解。検証結果と生成元アルゴリズムを必ず伴う。"""

    # problem_ref: 永続化時は Problem の id。単発実行では None
    problem_ref: uuid.UUID | None = None
    status: Literal["valid", "invalid", "infeasible"]
    assignments: SolutionData
    # metrics: 目的の実測値。例 {"total_weight": 9} / {"labor_cost": 21500}
    metrics: dict[str, float] = Field(default_factory=dict)
    violations: list[ConstraintViolation] = Field(default_factory=list)
    produced_by: AlgorithmMeta

