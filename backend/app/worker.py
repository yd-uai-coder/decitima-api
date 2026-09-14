"""arq ワーカー。`uv run arq app.worker.WorkerSettings` で起動する
(docker-compose.yml の `worker` サービスがこのコマンドを実行する)。

ワーカーは FastAPI プロセスとは別プロセスで動くので、リクエストスコープの DB セッション
(`app/api/deps.py::SessionDep`)は使い回せない ── `on_startup` で専用のエンジン・
セッションファクトリ・Redis クライアントを作り、`ctx`(worker context dict)に積む
(arq の定番パターン)。

`solve_job` 本体は `SolveService.solve`をそのまま呼ぶ ── 同期 solve のロジックを
ここで重複させない(進行のルール #17)。結果は Job 行に書き戻す。
"""

from __future__ import annotations

import uuid
from typing import Any

from arq.connections import RedisSettings
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.core.config import settings
from app.repositories.job import JobRepository
from app.schemas.optimization import SolveRequest
from app.services.solve import SolveService
from app.schemas.simulation import SimulationRequest
from app.services.simulation import run_simulation

async def on_startup(ctx: dict[str, Any]) -> None:
    """ワーカー起動時に1度だけ、専用の DB エンジンと Redis クライアントを作る。"""
    engine = create_async_engine(settings.DATABASE_URL, pool_pre_ping=True)
    ctx["engine"] = engine
    ctx["session_factory"] = async_sessionmaker(engine, expire_on_commit=False)
    ctx["redis"] = Redis.from_url(settings.REDIS_URL, decode_responses=True)


async def on_shutdown(ctx: dict[str, Any]) -> None:
    """ワーカー終了時にエンジン・Redis 接続を後片付けする。"""
    await ctx["engine"].dispose()
    await ctx["redis"].aclose()


async def solve_job(ctx: dict[str, Any], job_id: str) -> None:
    """arq ワーカーが実行するジョブ本体。Job 行を読み、SolveService で解いて書き戻す。

    `SolveService` 自身のレート制限は `bypass_rate_limit=True` で無効にする ──
    投入時点で `JobService.enqueue` が `resource="job_submit"` として既に制限済みなので、
    ワーカー側で `resource="solve"` の制限を二重にかけない。
    """
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        jobs = JobRepository(session)
        job = await jobs.get_by_id(uuid.UUID(job_id))
        if job is None:
            return  # 通常は起こらない(投入直後に消される等)

        await jobs.update_status(job.id, status="running")
        await session.commit()

        request = SolveRequest.model_validate(job.payload["request"])
        try:
            outcome = await SolveService(session, ctx["redis"]).solve(
                user_id=job.user_id,
                request=request,
                bypass_rate_limit=True,
            )
        except Exception as exc:  # noqa: BLE001 ── ジョブの失敗は例外を握って Job 行に記録する
            await jobs.update_status(
                job.id,
                status="failed",
                payload={**job.payload, "error": str(exc)},
            )
            await session.commit()
            return

        await jobs.update_status(
            job.id,
            status="succeeded",
            payload={
                **job.payload,
                "result": outcome.solution.model_dump(mode="json"),
                "problem_id": str(outcome.problem_id) if outcome.problem_id else None,
                "solution_id": str(outcome.solution_id) if outcome.solution_id else None,
            },
        )
        await session.commit()


async def simulate_job(ctx: dict[str, Any], job_id: str) -> None:
    """arq ワーカーが実行する simulate ジョブ本体(Phase 10-4)。`run_simulation` は
    session/redis に依存しない純粋なオーケストレーションなので、そのまま呼ぶだけでよい
    (`solve_job` のように `SolveService` をインスタンス化する必要が無い)。"""
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        jobs = JobRepository(session)
        job = await jobs.get_by_id(uuid.UUID(job_id))
        if job is None:
            return

        await jobs.update_status(job.id, status="running")
        await session.commit()

        request = SimulationRequest.model_validate(job.payload["request"])
        try:
            result = await run_simulation(request)
        except Exception as exc:  # noqa: BLE001 ── ジョブの失敗は例外を握って Job 行に記録する
            await jobs.update_status(
                job.id,
                status="failed",
                payload={**job.payload, "error": str(exc)},
            )
            await session.commit()
            return

        await jobs.update_status(
            job.id,
            status="succeeded",
            payload={**job.payload, "result": result.model_dump(mode="json")},
        )
        await session.commit()


class WorkerSettings:
    """arq CLI(`arq app.worker.WorkerSettings`)が読む設定。"""

    functions = [solve_job, simulate_job]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
