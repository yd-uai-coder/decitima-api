"""GET /api/v1/solutions/{id} / GET /api/v1/problems/{id} /
GET /api/v1/problems/{id}/solutions ── 永続化された問題・解の取得。

所有者スコープ(他ユーザーのものは 404)。
"""

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, SessionDep
from app.schemas.optimization import ProblemRead, SolutionRead
from app.services.optimization_read import OptimizationReadService

router = APIRouter(tags=["solutions"])


@router.get("/solutions/{solution_id}", response_model=SolutionRead)
async def get_solution(
    solution_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> SolutionRead:
    """保存済みの解 1 件を返す。"""
    row = await OptimizationReadService(session).get_solution(solution_id, user_id=current_user.id)
    return SolutionRead.model_validate(row)


@router.get("/problems/{problem_id}", response_model=ProblemRead)
async def get_problem(
    problem_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> ProblemRead:
    """保存済みの問題 1 件を返す。"""
    row = await OptimizationReadService(session).get_problem(problem_id, user_id=current_user.id)
    return ProblemRead.model_validate(row)


@router.get("/problems/{problem_id}/solutions", response_model=list[SolutionRead])
async def list_problem_solutions(
    problem_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> list[SolutionRead]:
    """ある問題に対する全解(複数アルゴリズム分。本格利用は Phase 3)。"""
    rows = await OptimizationReadService(session).list_solutions_for_problem(
        problem_id, user_id=current_user.id
    )
    return [SolutionRead.model_validate(r) for r in rows]
