"""共通スキーマの中核(アグリゲータ)。
- Objective / ConstraintBase(+ 判別子付きサブタイプ)/ GenericConstraint / AnyConstraint
- ProblemData(problem_type を判別子にした判別可能ユニオン)
- OptimizationProblem
"""

## 共通スキーマ -----------------------------------------
# LLMと Algorithm Engine の間に置く「共通言語」
# LLMからの回答を構造化して統一された型でアルゴリズムに渡す
#  ->アルゴリズムを差し替えても動作が保証される
#    複数アルゴリズムに同一のデータを渡して結果を比較できる
# ------------------------------------------------------

from __future__ import annotations


#@model_validatorについての補足
##モデル全体に対してバリデーション（検証）を行うためのデコレータ
##複数のフィールドを組み合わせてチェックしたい場合に使い
from pydantic import BaseModel, Field, model_validator

from typing import Literal, Annotated, Any

# 個別問題(葉)のインポート
from app.domain.problems.route_planner import RouteData
from app.domain.problems.shift_scheduler import ShiftData
from app.domain.problems.network_design import NetworkDesignData
from app.domain.problems.travel_planner import TravelData

# ---------------------------------------------------------------------------
# 目的(Objective)
# ---------------------------------------------------------------------------

class Objective(BaseModel):
    """最適化の目的を1つ表す。何を、どちら方向に良くしたいか。"""

    # sense: どちら方向に良くしたいか。（最小化 or 最大化 ）
    sense: Literal["minimize", "maximize"]
    # target: 対象メトリクスの名前。計算方法はアルゴリズム側が解釈する
    target: str
    # weight: 多目的のときの相対的な重み。単一目的なら 1.0 のまま
    weight: float = 1.0
    description: str | None = None


# ---------------------------------------------------------------------------
# 制約(Constraint)
# ---------------------------------------------------------------------------

class ConstraintBase(BaseModel):
    # 基底に kind: str を置いてサブクラスで Literal に狭めると
    # pyright standard が reportIncompatibleVariableOverride を出すため
    """全サブタイプ共通のフィールドだけ。
    判別子 kind は各サブタイプが宣言する。
    """

    # severity: hard=絶対に破れない / soft=破れるがペナルティが付く
    severity: Literal["hard", "soft"] = "hard"
    # penalty: soft 制約を1件破るごとに目的関数へ加算するペナルティ
    penalty: float | None = None
    description: str | None = None


class ForbiddenConstraint(ConstraintBase):
    """解に含めてはならない要素を列挙する制約(通行禁止エッジ等)。"""

    kind: Literal["forbidden"] = "forbidden" 
    items: list[str]


class NumericBoundConstraint(ConstraintBase):
    """ある数値フィールドの上限・下限・等値を課す宣言的な制約。"""

    kind: Literal["numeric_bound"] = "numeric_bound"
    # field: 対象フィールド名（例: "weekly_work_hours"）
    field: str
    operator: Literal["<=", ">=", "==", "<", ">"]
    value: float

class RequiredInclusionConstraint(ConstraintBase):
    """解に必ず含めなければならない要素を列挙する制約（必須経由ノード等）。"""

    kind: Literal["required_inclusion"] = "required_inclusion"
    items: list[str]


class ForbiddenConstraint(ConstraintBase):
    """解に含めてはならない要素を列挙する制約（通行禁止エッジ等）。"""

    kind: Literal["forbidden"] = "forbidden"
    items: list[str]


class StaffingConstraint(ConstraintBase):
    """各スロットの必要人数を満たすことを要求する制約（詳細は data 側が持つ）。"""

    kind: Literal["staffing"] = "staffing"


class GenericConstraint(ConstraintBase):
    """専用サブタイプのない ad-hoc な制約。kind は任意の文字列。
    種類が固まったら専用サブタイプに昇格させる。ここは基底ではなく末端なので
    kind: str の宣言でも override 警告は出ない。
    """

    kind: str

# constraints のいずれかの型を返すためAnnotated[]で指定している。
type AnyConstraint = Annotated[
    NumericBoundConstraint
    | RequiredInclusionConstraint
    | ForbiddenConstraint
    | StaffingConstraint
    | GenericConstraint,
    Field(union_mode="left_to_right"),
]

# ---------------------------------------------------------------------------
# 問題定義（OptimizationProblem）
# ---------------------------------------------------------------------------

##ユニオンの合成
type ProblemData = Annotated[
    RouteData | ShiftData | NetworkDesignData | TravelData , Field(discriminator="problem_type")
]

class OptimizationProblem(BaseModel):
    """LLM と Algorithm Engine の共通言語。目的・制約・問題固有データを束ねる。"""

    problem_type: Literal["route_planning", "shift_scheduling", "network_design", "travel_planning"]
    objectives: list[Objective]
    constraints: list[AnyConstraint] = Field(default_factory=list)
    data: ProblemData
    metadata: dict[str, Any] = Field(default_factory=dict)

    
    @model_validator(mode="after")
    def _problem_type_matches_data(self) -> OptimizationProblem:
        """トップの problem_type と data.problem_type の不一致を早期に弾く(Input Validation)。"""
        if self.problem_type != self.data.problem_type:
            raise ValueError(
                f"problem_type={self.problem_type!r} does not match "
                f"data.problem_type={self.data.problem_type!r}"
            )
        return self
