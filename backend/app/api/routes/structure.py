"""structure API ── 自然言語を `OptimizationProblem` へ構造化する。

POST /api/v1/structure   自然言語 → problem_type 分類 → objectives/constraints/data 抽出
                          → Validation。返る `problem` はそのまま POST /api/v1/solve に渡せる。

以前(テンプレート由来)の `POST /chat`(`app/api/routes/chat.py`)は Web検索QA機能の廃止に
伴い削除した。ルートは薄く: サービスを呼ぶ → スキーマに詰めて返すだけ(`solve.py` と同じ設計)。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.schemas.structuring import StructuringRequest, StructuringResponse
from app.services.structuring import ProblemStructuringService

router = APIRouter(prefix="/structure", tags=["structure"])


@router.post("", response_model=StructuringResponse)
async def structure_problem(
    payload: StructuringRequest,
    session: SessionDep,
    redis: RedisDep,
    current_user: CurrentUserDep,
) -> StructuringResponse:
    """自然言語を構造化する。"""
    service = ProblemStructuringService(session, redis)
    conversation, problem = await service.structure(
        user_id=current_user.id,
        conversation_id=payload.conversation_id,
        text=payload.text,
        bypass_rate_limit=current_user.is_superuser,
    )
    return StructuringResponse(
        conversation_id=conversation.id,
        problem_type=problem.problem_type,
        problem=problem,
    )
