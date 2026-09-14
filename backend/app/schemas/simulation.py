"""simulate API のリクエスト・レスポンススキーマ。

「What-if Simulation」── 既存の `OptimizationProblem` を「一部の値を変えて
複製」し、複数シナリオを解いて比較する。ドメイン別の override コードは持たず、
`overrides` は汎用の部分 dict(RFC 7386 JSON Merge Patch 相当。`services/simulation.py` の
`apply_overrides` がマージする)。problem_type やドメインスキーマ自体は不変。
"""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field, model_validator

from app.domain.problems.problem import OptimizationProblem

class ScenarioOverride(BaseModel):
    """シナリオ1件。`overrides` は base problem への部分 dict(dict は再帰マージ、
    list やスカラーは丸ごと置換。値が None ならそのキーを削除)。"""

    label: str
    overrides: dict[str, Any] = Field(default_factory=dict)


class SensitivitySpec(BaseModel):
    """感度分析(閾値発見)の指定。`field_path` はドット区切りの dict キーのみ
    (例: "data.resource_capacity")── list の添字は対象外(merge patch は list を丸ごと
    置換するため、要素単位の上書きには向かない)。[low, high] の整数を二分探索で走査し、
    evaluate(param) が target_metric について threshold を満たす最小の param を探す。
    """

    field_path: str
    low: int
    high: int
    target_metric: str
    threshold: float
    mode: Literal["at_most", "at_least"] = "at_most"

    @model_validator(mode="after")
    def _range_is_valid(self) -> SensitivitySpec:
        if self.low > self.high:
            raise ValueError(f"low({self.low}) must be <= high({self.high})")
        return self


class SimulationRequest(BaseModel):
    """simulate API のリクエスト。base problem + シナリオ群(+ 任意で感度分析)。"""

    problem: OptimizationProblem
    # algorithm: None なら base problem に対して自動選択し、その名前を全シナリオに固定する
    # (条件だけを変え、アルゴリズム選択の揺れを比較に混ぜないため)
    algorithm: str | None = None
    scenarios: list[ScenarioOverride] = Field(min_length=1)
    sensitivity: SensitivitySpec | None = None
    timeout_seconds: float | None = Field(default=None, gt=0)


class ScenarioResult(BaseModel):
    """1 シナリオの solve 結果の要約。override が invalid / infeasible / 該当アルゴリズム無し
    になった場合は例外にせず status="invalid_scenario" として記録する(他シナリオは続行)。"""

    label: str
    status: Literal["valid", "invalid", "infeasible", "invalid_scenario"]
    metrics: dict[str, float] = Field(default_factory=dict)
    algorithm_name: str | None = None
    error: str | None = None  # invalid_scenario のときだけ入る

class SensitivityResult(BaseModel):
    """感度分析の結果。範囲内に条件を満たす点が無ければ threshold_value は None。

    `evaluated` は二分探索が実際に評価した param → target_metric の値(全件スイープとの
    対比・分析トラックの tornado chart 用集計(Phase 10-5)に使う)。"""

    threshold_value: int | None
    evaluated: dict[int, float]


class SimulationResult(BaseModel):
  """simulate ジョブの最終結果。base = override 無しの元の問題の solve 結果。"""

  base: ScenarioResult
  scenarios: list[ScenarioResult]
  sensitivity: SensitivityResult | None = None
