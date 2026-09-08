"""POST /api/v1/solve ── 構造化問題を解いて検証済みの解を返す(本流)。

ルートは薄く: サービスを呼ぶ → スキーマに詰めて返すだけ。例外処理は書かない
(SolveService 内で AppError 派生が飛び、register_error_handlers が JSON 化する)。
"""

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.schemas.optimization import SolveRequest, SolveResponse
from app.services.solve import SolveService

router = APIRouter(prefix="/solve", tags=["solve"])


@router.post("", response_model=SolveResponse)
async def solve(
    payload: SolveRequest,
    session: SessionDep,
    redis: RedisDep,
    current_user: CurrentUserDep,
) -> SolveResponse:
    """構造化された最適化問題を受け取り、決定論的に解いて検証済みの解を返す。"""
    outcome = await SolveService(session, redis).solve(
        user_id=current_user.id,
        request=payload,
        bypass_rate_limit=current_user.is_superuser,
    )
    return SolveResponse(
        solution=outcome.solution,
        problem_id=outcome.problem_id,
        solution_id=outcome.solution_id,
    )
