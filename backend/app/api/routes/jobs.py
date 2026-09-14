# DeciTima samples │ Phase 9
"""作業単位 9-8: jobs API ── 重い solve をジョブキュー(arq)経由で非同期実行する。

POST /api/v1/jobs        投入。202 Accepted + job_id を返す(結果はポーリングで取得)。
GET  /api/v1/jobs/{id}   状態・結果のポーリング。

既存の同期 `POST /api/v1/solve`(Phase 1)は無変更で併存する。ルートは薄く:
サービスを呼ぶ → スキーマに詰めて返すだけ(`solve.py` と同じ設計、Phase-0-7.md §4)。
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException, status

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.schemas.job import JobStatusResponse, JobSubmitResponse
from app.schemas.optimization import SolveRequest
from app.services.job import JobService

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobSubmitResponse, status_code=status.HTTP_202_ACCEPTED)
async def submit_job(
    payload: SolveRequest,
    session: SessionDep,
    redis: RedisDep,
    current_user: CurrentUserDep,
) -> JobSubmitResponse:
    """solve をジョブとして投入する。"""
    job = await JobService(session, redis).enqueue(
        user_id=current_user.id,
        request=payload,
        bypass_rate_limit=current_user.is_superuser,
    )
    return JobSubmitResponse(job_id=job.id, status=job.status)


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job(
    job_id: uuid.UUID,
    session: SessionDep,
    redis: RedisDep,
    current_user: CurrentUserDep,
) -> JobStatusResponse:
    """ジョブの状態をポーリングする。succeeded なら result に検証済みの解が入る。"""
    job = await JobService(session, redis).get_status(job_id)
    if job is None or (job.user_id != current_user.id and not current_user.is_superuser):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="job not found")
    payload = job.payload
    return JobStatusResponse(
        job_id=job.id,
        problem_type=job.problem_type,
        status=job.status,
        result=payload.get("result"),
        problem_id=payload.get("problem_id"),
        solution_id=payload.get("solution_id"),
        error=payload.get("error"),
        created_at=job.created_at,
        updated_at=job.updated_at,
    )
