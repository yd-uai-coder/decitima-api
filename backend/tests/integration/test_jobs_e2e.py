# DeciTima samples │ Phase 9
"""作業単位 9-8: ジョブキューの end-to-end(実 PostgreSQL + 実 Redis + arq)。
作業単位 10-4: simulate ジョブの e2e を追加(`simulate_job`)。

@pytest.mark.integration ── `docker compose up postgres redis` の上で
`uv run pytest -m integration` したときだけ走る(既定では除外)。`JobService.enqueue` が
実際に Redis へジョブを積み、arq 側からステータスが追えることを確認する。実ワーカー
プロセス(`uv run arq app.worker.WorkerSettings`)は起動しない(CI 簡素化)── ジョブの
処理そのものは `app.worker.solve_job` を直接呼んで検証する(9-8 のユニットテストと同じ形)。
ここでは「本当に Redis へ積めるか / arq 側の Job オブジェクトから状態が見えるか」に絞る。
"""

from collections.abc import AsyncGenerator

import pytest
import pytest_asyncio
from arq import create_pool
from arq.connections import RedisSettings
from arq.jobs import Job as ArqJob
from arq.jobs import JobStatus as ArqJobStatus
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from tests.fixtures.optimization import build_project_problem, build_route_problem

import app.models  # noqa: F401  Base.metadata に Job/Problem/Solution/User を登録
from app.core.config import settings
from app.core.database import Base, engine
from app.models.user import User
from app.repositories.job import JobRepository
from app.schemas.optimization import SolveRequest
from app.schemas.simulation import ScenarioOverride, SimulationRequest
from app.services.job import JobService
from app.worker import solve_job
from app.worker import simulate_job, solve_job
from tests.integration.conftest import ensure_test_database

pytestmark = pytest.mark.integration


@pytest_asyncio.fixture
async def pg_session() -> AsyncGenerator[AsyncSession]:
    """実 Postgres に対して、毎回まっさらなスキーマで非同期セッションを提供する。"""
    ensure_test_database()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    async with factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    # 写経の罠: engine はプロセス全体で 1 つのシングルトン(app.core.database)だが、
    # pytest-asyncio はテスト関数ごとに新しい event loop を作る。ここで dispose しないと
    # プールに残った接続(前のテストの event loop に紐付いている)が次のテスト(別の
    # event loop)で pool_pre_ping の ping に使われ、
    # `RuntimeError: ... attached to a different loop` になる(このファイルに2本目の
    # テストを追加して初めて顕在化した)。
    await engine.dispose()


async def test_enqueue_reaches_redis_and_solve_job_processes_it(
    pg_session: AsyncSession,
) -> None:
    user = User(email="jobqueue@example.com", hashed_password="x")
    pg_session.add(user)
    await pg_session.flush()

    real_redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    job = await JobService(pg_session, real_redis).enqueue(
        user_id=user.id, request=SolveRequest(problem=build_route_problem())
    )

    # 実際に Redis 上のキューへ積まれているか(_job_id を Job.id に揃えてあるので直接引ける)
    pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    try:
        arq_job = ArqJob(str(job.id), pool)
        assert await arq_job.status() == ArqJobStatus.queued

        # 実ワーカーは起動せず、同じ関数を直接呼んでジョブを「処理」する
        ctx = {
            "session_factory": async_sessionmaker(engine, expire_on_commit=False),
            "redis": real_redis,
        }
        await solve_job(ctx, str(job.id))
    finally:
        await pool.aclose()
        await real_redis.aclose()

    # 写経の罠: ここで pg_session をそのまま使うと、enqueue 時に作った job インスタンスが
    # identity map に残ったまま(expire_on_commit=False)なので session.get() がそれを
    # 返し、solve_job が別セッションで書いた更新(status="succeeded")が見えない ──
    # 実際の GET /jobs/{id} は毎リクエスト新規セッション(get_db)を使うので、検証もそれに
    # 合わせて新しいセッションで読み直す。
    async with async_sessionmaker(engine, expire_on_commit=False)() as verify_session:
        row = await JobRepository(verify_session).get_by_id(job.id)
        assert row is not None
        assert row.status == "succeeded"
        assert row.payload["result"]["status"] == "valid"


async def test_enqueue_simulation_reaches_redis_and_simulate_job_processes_it(
    pg_session: AsyncSession,
) -> None:
    """作業単位 10-4: solve ジョブと同型の e2e。`simulate_job` を直接呼んで処理する。"""
    user = User(email="simqueue@example.com", hashed_password="x")
    pg_session.add(user)
    await pg_session.flush()

    real_redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    request = SimulationRequest(
        problem=build_project_problem(),
        scenarios=[ScenarioOverride(label="tighter", overrides={"data": {"resource_capacity": 1}})],
    )
    job = await JobService(pg_session, real_redis).enqueue_simulation(
        user_id=user.id, request=request
    )

    pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
    try:
        arq_job = ArqJob(str(job.id), pool)
        assert await arq_job.status() == ArqJobStatus.queued

        ctx = {
            "session_factory": async_sessionmaker(engine, expire_on_commit=False),
            "redis": real_redis,
        }
        await simulate_job(ctx, str(job.id))
    finally:
        await pool.aclose()
        await real_redis.aclose()

    # 写経の罠(9-8 と同じ): identity map を避けて新しいセッションで読み直す
    async with async_sessionmaker(engine, expire_on_commit=False)() as verify_session:
        row = await JobRepository(verify_session).get_by_id(job.id)
        assert row is not None
        assert row.status == "succeeded"
        assert row.payload["result"]["base"]["status"] == "valid"
        assert row.payload["result"]["scenarios"][0]["label"] == "tighter"
