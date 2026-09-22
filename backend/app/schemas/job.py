"""jobs API のリクエスト・レスポンススキーマ。

ジョブ投入のリクエストは `schemas/optimization.py::SolveRequest`(solve ジョブ)または
`schemas/simulation.py::SimulationRequest`(simulate ジョブ、Phase 10-4)をそのまま再利用する。
新規に定義するのはレスポンス(投入直後のステータス、ポーリング結果)だけ。

`JobStatusResponse.result` を simulate ジョブの結果も返せるように広げた
(`JobResult`)。`CandidateSolution` と `SimulationResult` は必須フィールドが重ならない
(前者は status/assignments/produced_by、後者は base/scenarios)ため、判別用の kind タグを
持たない素の union でも Pydantic の smart union がどちらの形か判別できる。
`app/worker.py::solve_job` の書き込み方は変えていない(Phase 9-8 の e2e テストは無改造)。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from pydantic import BaseModel

from app.domain.solutions.solution import CandidateSolution
from app.schemas.simulation import SimulationResult

if TYPE_CHECKING:
    from app.models.job import Job

type JobResult = CandidateSolution | SimulationResult


class JobSubmitResponse(BaseModel):
    """POST /jobs のレスポンス。202 Accepted とともに返す(結果は GET /jobs/{id} でポーリング)。"""

    job_id: uuid.UUID
    status: str  # 投入直後は常に "queued"


class JobStatusResponse(BaseModel):
    """GET /jobs/{id} のレスポンス。status に応じて result / error のどちらかが埋まる。"""

    job_id: uuid.UUID
    problem_type: str
    status: str  # "queued" | "running" | "succeeded" | "failed"
    result: JobResult | None = None  # succeeded のときだけ入る
    problem_id: uuid.UUID | None = None
    solution_id: uuid.UUID | None = None
    error: str | None = None  # failed のときだけ入る
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_job(cls, job: Job) -> JobStatusResponse:
        """Job 行(検索キー = カラム、結果類 = payload)からレスポンスを組み立てる。
        payload のキー名(result / problem_id / solution_id / error)の知識はここに集約する。"""
        payload = job.payload
        return cls(
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
