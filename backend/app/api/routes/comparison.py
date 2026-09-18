"""POST /api/v1/compare ── 「LLM vs Algorithm Comparison」。

薄いルート ── サービスを呼んでスキーマに詰めるだけ。永続化しない(GET エンドポイントは無い)。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, RedisDep
from app.schemas.comparison import ComparisonRequest, ComparisonResponse
from app.services.comparison import ComparisonService

router = APIRouter(tags=["comparison"])


@router.post("/compare", response_model=ComparisonResponse)
async def compare_llm_vs_algorithm(
    payload: ComparisonRequest,
    redis: RedisDep,
    current_user: CurrentUserDep,
) -> ComparisonResponse:
    """同一問題を Algorithm 経路と LLM Only 経路の両方で解き、6軸で比較する。"""
    return await ComparisonService(redis).compare(
        user_id=current_user.id,
        request=payload,
        bypass_rate_limit=current_user.is_superuser,
    )
