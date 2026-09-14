# DeciTima samples │ Phase 10
"""作業単位 10-4: simulate API ── 複数シナリオを非同期ジョブとして投入する。

POST /api/v1/simulate    投入。202 Accepted + job_id を返す(結果はポーリングで取得)。

結果のポーリングは既存の `GET /api/v1/jobs/{id}`(Phase 9-8)をそのまま再利用する ──
`JobStatusResponse.result` の型を Phase 10-4 で広げてあるので、専用の GET エンドポイントは
新設しない(進行のルール #17: 実消費者が既にあるものを増やさない)。
"""

from __future__ import annotations

from fastapi import APIRouter, status

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.schemas.job import JobSubmitResponse
from app.schemas.simulation import SimulationRequest
from app.services.job import JobService

router = APIRouter(tags=["simulate"])


@router.post("/simulate", response_model=JobSubmitResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_simulation(
    payload: SimulationRequest,
    session: SessionDep,
    redis: RedisDep,
    current_user: CurrentUserDep,
) -> JobSubmitResponse:
    """base problem + シナリオ群をジョブとして投入する。結果は GET /jobs/{id} でポーリングする。"""
    job = await JobService(session, redis).enqueue_simulation(
        user_id=current_user.id,
        request=payload,
        bypass_rate_limit=current_user.is_superuser,
    )
    return JobSubmitResponse(job_id=job.id, status=job.status)
