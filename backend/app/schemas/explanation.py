"""Result Explanation の API スキーマ + LLM 構造化出力スキーマ。

`ExplanationResponse` が `POST /api/v1/solutions/{solution_id}/explain` の対外契約。
`LlmExplanation` は `with_structured_output()` に渡す LLM 専用スキーマ
(`app/schemas/recommendation.py` の `LlmRecommendation` と同じ「API 契約と LLM 契約を
同じファイルに置く」流儀)。

5フィールドは 説明対象5項目に1:1対応する:
なぜこの解になったか / どの制約が重要だったか / どのアルゴリズムを使ったか /
他の候補との違い / 改善余地。
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class LlmExplanation(BaseModel):
    """LLM の構造化出力全体(説明対象5項目そのまま)。"""

    why_this_solution: str  # なぜこの解になったか
    key_constraints: str  # どの制約が重要だったか(hard/soft violations を踏まえて)
    algorithm_rationale: str  # どのアルゴリズムを使ったか、その特徴
    alternatives_comparison: str  # 他の候補アルゴリズムとの違い
    improvement_notes: str  # 改善余地(soft違反・未達目的があれば)


class ExplanationResponse(BaseModel):
    """POST /api/v1/solutions/{solution_id}/explain のレスポンス。

    # solution_id / problem_type / algorithm_name: どの解を、何のアルゴリズムで説明したか
    # why_this_solution 〜 improvement_notes: LlmExplanation の5フィールドをそのまま転記
    #                                          (LLM失敗時は機械的なフォールバック文言になる)
    # notes: 「LLM 呼び出しに失敗したため機械的な要約のみ返している」等の補足
    """

    solution_id: uuid.UUID
    problem_type: str
    algorithm_name: str
    why_this_solution: str
    key_constraints: str
    algorithm_rationale: str
    alternatives_comparison: str
    improvement_notes: str
    notes: list[str] = Field(default_factory=list)
