"""Algorithm Recommendation の API スキーマ + LLM 構造化出力スキーマ。

`RecommendRequest`/`RecommendationResponse`/`AlgorithmRecommendation` が
`POST /api/v1/algorithms/recommend` の対外契約。`LlmRecommendation`/`LlmAlgorithmComment` は
`with_structured_output()` に渡す LLM 専用スキーマ(`app/schemas/structuring.py` の
`ObjectivesConstraintsExtraction` 等と同じ「API 契約と LLM 契約を同じファイルに置く」流儀)。
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.problems.problem import OptimizationProblem


class RecommendRequest(BaseModel):
    """POST /api/v1/algorithms/recommend のリクエスト。構造化済みの問題をそのまま渡す
    (`/verify` の `VerifyRequest` と同じ「DB を介さず body でそのまま受け取る」設計)。"""

    problem: OptimizationProblem


class AlgorithmRecommendation(BaseModel):
    """候補アルゴリズム1件の情報と、ルール/LLM それぞれの見解。

    # name: registry 上の meta.name(例: "knapsack_dp")
    # family / implementation / time_complexity: AlgorithmMeta からそのまま転記
    # description: 静的な1行説明(_ALGORITHM_DESCRIPTIONS から)
    # is_rule_preferred: 既存 select_strategy が選んだ候補かどうか
    # llm_rank: LLM のおすすめ順(1が最も推奨)。LLM 呼び出しをしなかった/失敗した場合は None
    # llm_comment: LLM が付けた一言コメント。同上の理由で None になり得る
    """

    name: str
    family: str
    implementation: str
    time_complexity: str | None = None
    description: str
    is_rule_preferred: bool
    llm_rank: int | None = None
    llm_comment: str | None = None


class RecommendationResponse(BaseModel):
    """POST /api/v1/algorithms/recommend のレスポンス。

    # rule_preferred: 既存 select_strategy が選ぶ meta.name(参考情報として必ず返す)
    # recommendations: 登録済み全候補(1件のみなら1件)。LLM のランクが付いたものを先頭に、
    #                   付かなかったものは registry 順のまま末尾に残す
    # notes: 「候補が1件のみのため LLM 未呼び出し」「LLM 呼び出し失敗」等の補足
    """

    problem_type: str
    rule_preferred: str
    recommendations: list[AlgorithmRecommendation]
    notes: list[str] = Field(default_factory=list)


class LlmAlgorithmComment(BaseModel):
    """LLM が1候補に付けた一言コメント(構造化出力用)。"""

    name: str
    comment: str


class LlmRecommendation(BaseModel):
    """LLM の構造化出力全体。

    # ranked_names: 推薦順(先頭が最も推奨)。存在しない候補名を含み得る(grounding は
    #               呼び出し側の service で行う ── ground_references と同じ「LLM出力は
    #               常に信頼しない」の徹底)
    # comments: 候補ごとの一言コメント
    """

    ranked_names: list[str]
    comments: list[LlmAlgorithmComment]
