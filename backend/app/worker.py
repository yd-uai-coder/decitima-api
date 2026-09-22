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

import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from arq.connections import RedisSettings
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.errors import AppError
from app.models.job import Job
from app.repositories.job import JobRepository
from app.schemas.optimization import SolveRequest
from app.schemas.simulation import SimulationRequest
from app.services.simulation import run_simulation
from app.services.solve import SolveService

# 各ジョブ種別の実処理。(session, job)を受け取り、成功時に Job.payload へマージする
# フィールド(result など)を返す。失敗は例外で表す(`_run_job` が failed として記録する)。
type JobRunner = Callable[[AsyncSession, Job], Awaitable[dict[str, Any]]]

logger = logging.getLogger(__name__)

# 利用者に返してよくない(内部事情を含み得る)失敗に使う固定メッセージ
_INTERNAL_ERROR_MESSAGE = "internal error"


def _public_error_message(exc: Exception) -> str:
    """Job.payload["error"](= GET /jobs/{id} でそのまま返る)に書く文言を決める。
    `AppError`(検証 NG・該当アルゴリズム無し・タイムアウト等)は利用者向けに書かれた文言なので
    そのまま返す。それ以外(DB エラー・想定外の例外)は SQL 断片やパスを含み得るため固定文言にし、
    詳細は `logger.exception` に残す(診断書 §6-6)。"""
    return str(exc) if isinstance(exc, AppError) else _INTERNAL_ERROR_MESSAGE


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


async def _run_job(ctx: dict[str, Any], job_id: str, runner: JobRunner) -> None:
    """ジョブ 1 件の状態遷移(queued -> running -> succeeded/failed)と書き戻しを担う共通本体。
    solve / simulate の違いは `runner` だけ ── 失敗の扱い(failed + error 記録)を 1 か所に
    保つため、ジョブ種別を増やしても状態遷移のコードは増やさない。"""
    session_factory = ctx["session_factory"]
    async with session_factory() as session:
        jobs = JobRepository(session)
        job = await jobs.get_by_id(uuid.UUID(job_id))
        if job is None:
            return  # 通常は起こらない(投入直後に消される等)

        await jobs.update_status(job.id, status="running")
        await session.commit()

        # rollback で ORM オブジェクトが expire されるため、必要な値を先に控えておく
        pk = job.id
        problem_type = job.problem_type
        base_payload = job.payload
        try:
            fields = await runner(session, job)
        except Exception as exc:  # noqa: BLE001 ── ジョブの失敗は例外を握って Job 行に記録する
            logger.exception("job %s (%s) failed", pk, problem_type)
            # runner 内の DB エラー(flush 失敗等)でセッションが「要 rollback」状態になり得る。
            # 先に rollback しないと次の update_status も失敗し、Job が running のまま固着する。
            await session.rollback()
            await jobs.update_status(
                pk,
                status="failed",
                payload={**base_payload, "error": _public_error_message(exc)},
            )
            await session.commit()
            return

        await jobs.update_status(pk, status="succeeded", payload={**base_payload, **fields})
        await session.commit()


async def solve_job(ctx: dict[str, Any], job_id: str) -> None:
    """arq ワーカーが実行する solve ジョブ本体。`SolveService` で解いて結果を書き戻す。

    `SolveService` 自身のレート制限は `bypass_rate_limit=True` で無効にする ──
    投入時点で `JobService.enqueue` が `resource="job_submit"` として既に制限済みなので、
    ワーカー側で `resource="solve"` の制限を二重にかけない。
    """

    async def runner(session: AsyncSession, job: Job) -> dict[str, Any]:
        request = SolveRequest.model_validate(job.payload["request"])
        outcome = await SolveService(session, ctx["redis"]).solve(
            user_id=job.user_id,
            request=request,
            bypass_rate_limit=True,
        )
        return {
            "result": outcome.solution.model_dump(mode="json"),
            "problem_id": str(outcome.problem_id) if outcome.problem_id else None,
            "solution_id": str(outcome.solution_id) if outcome.solution_id else None,
        }

    await _run_job(ctx, job_id, runner)


async def simulate_job(ctx: dict[str, Any], job_id: str) -> None:
    """arq ワーカーが実行する simulate ジョブ本体(Phase 10-4)。`run_simulation` は
    session/redis に依存しない純粋なオーケストレーションなので、そのまま呼ぶだけでよい
    (`solve_job` のように `SolveService` をインスタンス化する必要が無い)。"""

    async def runner(_session: AsyncSession, job: Job) -> dict[str, Any]:
        request = SimulationRequest.model_validate(job.payload["request"])
        result = await run_simulation(request)
        return {"result": result.model_dump(mode="json")}

    await _run_job(ctx, job_id, runner)


class WorkerSettings:
    """arq CLI(`arq app.worker.WorkerSettings`)が読む設定。"""

    functions = [solve_job, simulate_job]
    on_startup = on_startup
    on_shutdown = on_shutdown
    redis_settings = RedisSettings.from_dsn(settings.REDIS_URL)
    max_jobs = settings.WORKER_MAX_JOBS
