"""LLM の Structured Output 用スキーマと、Structuring API のリクエスト/レスポンス。

自然言語から LLM が直接埋めてよいのは「problem_type 分類」「objectives / constraints」
「data のトップレベル・スカラー/辞書フィールド」までで、ノード/エッジ/タスクのような
カタログ(list)フィールドはベース問題(app/domain/problems/base_problems.py)から引き継ぐ
(README「LLM 出力は常に信頼しない」── カタログをでっち上げさせない設計)。

*DataPatch は対応する Data クラス(RouteData 等)のトップレベル・スカラーだけを Optional で
抜き出した「LLM向け簡易スキーマ」。全フィールド Optional にして、LLM が触れなかった項目は
None のまま(= 変更しない)にする。network_design はトップレベル・スカラーを持たないため
Patch クラスを作らない(11-2 の EXTRACTORS で None を登録する)。
"""

from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, Field

from app.domain.problems.problem import OptimizationProblem

ProblemTypeLiteral = Literal[
    "route_planning",
    "shift_scheduling",
    "network_design",
    "travel_planning",
    "project_scheduling",
    "logistics_planning",
]


class ProblemTypeClassification(BaseModel):
    """自然言語がどの problem_type を指しているかの分類結果。"""

    problem_type: ProblemTypeLiteral


# ---------------------------------------------------------------------------
# objectives / constraints(ドメイン非依存、全 problem_type 共通の1スキーマ)
# ---------------------------------------------------------------------------


class ExtractedObjective(BaseModel):
    """Objective と同型。model_dump() がそのまま Objective の初期化引数になる。"""

    sense: Literal["minimize", "maximize"]
    target: str
    weight: float = 1.0
    description: str | None = None


class ExtractedConstraint(BaseModel):
    """AnyConstraint の全サブタイプのフィールドを1つに平らにした LLM向け簡易スキーマ。
    kind で判別し、model_dump(exclude_none=True) がそのまま AnyConstraint の
    discriminated union に再パースできる形にする(専用の変換関数を書かない)。"""

    kind: Literal["forbidden", "numeric_bound", "required_inclusion", "staffing", "generic"]
    severity: Literal["hard", "soft"] = "hard"
    penalty: float | None = None
    description: str | None = None
    items: list[str] | None = None  # forbidden / required_inclusion 用(実在する id を使う)
    field: str | None = None  # numeric_bound 用
    operator: Literal["<=", ">=", "==", "<", ">"] | None = None  # numeric_bound 用
    value: float | None = None  # numeric_bound 用


class ObjectivesConstraintsExtraction(BaseModel):
    """extract_objectives_constraints ノードの Structured Output。"""

    objectives: list[ExtractedObjective] = Field(default_factory=list)
    constraints: list[ExtractedConstraint] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# data のトップレベル・スカラー(ドメインごとの簡易パッチ。実フィールドは各 *Data と対応)
# ---------------------------------------------------------------------------


class RouteDataPatch(BaseModel):
    """RouteData のトップレベル(nodes/edges は引き継ぐので含めない)。"""

    start: str | None = None
    goal: str | None = None
    allow_negative: bool | None = None


class TravelDataPatch(BaseModel):
    """TravelData のトップレベル(places/legs は引き継ぐので含めない)。"""

    budget: float | None = None
    time_budget: float | None = None
    start: str | None = None
    preferences: dict[str, float] | None = None


class ShiftDataPatch(BaseModel):
    """ShiftData のトップレベル(staff/slots は引き継ぐので含めない)。"""

    max_weekly_hours: float | None = None
    max_consecutive_days: int | None = None


class ProjectDataPatch(BaseModel):
    """ProjectData のトップレベル(tasks/dependencies は引き継ぐので含めない)。"""

    resource_capacity: int | None = None


class LogisticsDataPatch(BaseModel):
    """LogisticsData のトップレベル(nodes/segments/vehicles/deliveries は引き継ぐので含めない)。"""

    depot_id: str | None = None


# network_design(NetworkDesignData)はトップレベル・スカラーを持たないため Patch クラスは無い


# ---------------------------------------------------------------------------
# Structuring API
# ---------------------------------------------------------------------------


class StructuringRequest(BaseModel):
    """POST /api/v1/structure のリクエストボディ。"""

    # 上限は LLM に渡る入力(トークン課金・プロンプト注入の面積)を抑えるため。自然言語 1〜数文が想定
    text: str = Field(min_length=1, max_length=2000)
    conversation_id: uuid.UUID | None = None


class StructuringResponse(BaseModel):
    """POST /api/v1/structure のレスポンス。problem はそのまま POST /api/v1/solve に渡せる。"""

    conversation_id: uuid.UUID
    problem_type: ProblemTypeLiteral
    problem: OptimizationProblem
    notes: list[str] = Field(default_factory=list)
