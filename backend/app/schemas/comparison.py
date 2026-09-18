# DeciTima samples │ 初出 Phase 14
"""compare API の契約 + LLM ナレーションの契約。

6評価軸(制約遵守率・最適性・再現性・実行時間・
エラー率・検証可能性)を `ComparisonMetrics` に集計する。検証可能性は数値化しにくいため
`notes` / `ComparisonNarrative.verifiability_note` に定性的な説明として持たせる。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.problems.problem import OptimizationProblem
from app.domain.solutions.solution import AlgorithmMeta


class ComparisonRequest(BaseModel):
    """compare API のリクエスト。1問題を Algorithm 経路と LLM Only 経路の両方で解く。"""

    problem: OptimizationProblem
    algorithm: str | None = None  # 指定なければ rule-based 選択(select_strategy と同じ)
    llm_runs: int = Field(default=5, ge=1, le=20)  # LLM Only を再実行する回数(再現性測定)


class RunOutcome(BaseModel):
    """1回の実行結果。Algorithm は1回、LLM Only は llm_runs 回ぶん生成される。"""

    status: str | None = None  # "valid"/"invalid"/"infeasible"。例外で失敗した回は None
    metrics: dict[str, float] = Field(default_factory=dict)
    hard_violations: int = 0
    soft_violations: int = 0
    elapsed_ms: float = 0.0
    error: str | None = None  # 例外メッセージ(成功した回は None)
    # structure_hash: 解の構造(assignments)を要約した短いハッシュ。再現性(同じ構造が何回
    # 出たか)の集計に使う。生の assignments 全体を返すと llm_runs 分ペイロードが膨らむため
    # ハッシュだけ持つ(必要なら別途 solve/verify で個別に確認できる)。
    structure_hash: str | None = None


class ComparisonMetrics(BaseModel):
    """README §14 の6評価軸のうち、数値化できる5軸の集計値。"""

    constraint_compliance_rate_algorithm: float  # valid件数 / 試行数(Algorithmは1/1が既定)
    constraint_compliance_rate_llm: float  # valid件数 / 成功した試行数
    optimality_avg_quality_ratio_llm: float | None  # 1.0 = Algorithm と同等。値が大きいほど劣る
    reproducibility_distinct_solutions_llm: int  # 成功した llm_runs の中で構造が異なる解の種類数
    execution_time_ms_algorithm: float
    execution_time_ms_llm_median: float
    error_rate_llm: float  # 例外で失敗した回数 / 試行数


class ComparisonNarrative(BaseModel):
    """LLM に生成させる比較の要約文(README 説明対象5項目の Phase 14 版)。"""

    summary: str
    constraint_compliance_note: str
    optimality_note: str
    reproducibility_note: str
    verifiability_note: str  # 6軸目「検証可能性」は数値化せずここで定性的に説明する


class ComparisonResponse(BaseModel):
    """compare API のレスポンス。永続化しない(GET エンドポイントは無い)。"""

    problem_type: str
    algorithm_used: AlgorithmMeta
    algorithm_result: RunOutcome
    llm_results: list[RunOutcome]
    metrics: ComparisonMetrics
    narrative: ComparisonNarrative | None = None
    notes: list[str] = Field(default_factory=list)
