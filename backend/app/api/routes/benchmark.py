"""POST /api/v1/benchmark   ── 1 問題を複数アルゴリズムで解いて比較(実測を並べる)。
GET  /api/v1/benchmarks/{id} ── 保存済みベンチマーク実行の読み出し(所有者スコープ)。

"""

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentUserDep, RedisDep, SessionDep
from app.schemas.optimization import BenchmarkRequest, BenchmarkResponse, BenchmarkRunRead
from app.services.benchmark import BenchmarkService
from app.services.optimization_read import OptimizationReadService

router = APIRouter(tags=["benchmark"])


@router.post("/benchmark", response_model=BenchmarkResponse)
async def run_benchmark(
    payload: BenchmarkRequest,
    session: SessionDep,
    redis: RedisDep,
    current_user: CurrentUserDep,
) -> BenchmarkResponse:
    """問題 + アルゴリズム候補を受けて、各アルゴリズムの実測を返す。invalid 解も 200。"""
    outcome = await BenchmarkService(session, redis).run(
        user_id=current_user.id,
        request=payload,
        bypass_rate_limit=current_user.is_superuser,
    )
    return BenchmarkResponse(entries=outcome.entries, benchmark_id=outcome.benchmark_id)


@router.get("/benchmarks/{benchmark_id}", response_model=BenchmarkRunRead)
async def get_benchmark_run(
    benchmark_id: uuid.UUID, session: SessionDep, current_user: CurrentUserDep
) -> BenchmarkRunRead:
    """保存済みのベンチマーク実行 1 件を返す。"""
    row = await OptimizationReadService(session).get_benchmark_run(
        benchmark_id, user_id=current_user.id
    )
    return BenchmarkRunRead.model_validate(row)
