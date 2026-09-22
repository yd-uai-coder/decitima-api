"""作業単位 9-8: app/worker.py::solve_job(arq ワーカー本体)。Phase 15-5 で max_jobs のテストを追加。

テスト対象 / ドライバ / スタブ:
- 対象: `solve_job`(Job 行の状態遷移 queued -> running -> succeeded/failed、
  `SolveService.solve` への委譲、失敗時のエラー記録)
- ドライバ: このテスト関数。`on_startup` を経由せず、専用のインメモリ SQLite エンジン +
  `session_factory` を直接組み立てて `ctx` に積む(`tests/api/conftest.py` の `api` fixture と同型)
- スタブ: `FakeRedis`(`SolveService` のコンストラクタが要求するだけ ── `bypass_rate_limit=True`
  で呼ばれるので実際にはレート制限を通らない)。DB エンジンの生成(`on_startup`)自体は
  integration テストの領分。
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any, cast

import pytest
import pytest_asyncio
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from tests.fixtures.fake_redis import FakeRedis
from tests.fixtures.optimization import build_route_problem

import app.models  # noqa: F401  Base.metadata に Job/Problem/Solution/User を登録する
from app.core.database import Base
from app.models.user import User
from app.repositories.job import JobRepository
from app.schemas.optimization import SolveRequest
from app.worker import solve_job


@pytest_asyncio.fixture
async def ctx() -> AsyncGenerator[dict[str, Any]]:
    """`on_startup` を経由せず、テスト用のインメモリ DB + FakeRedis を積んだ ctx を用意する。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    yield {"session_factory": session_factory, "redis": cast(Redis, FakeRedis())}
    await engine.dispose()


async def _make_job(ctx: dict[str, Any], *, problem: Any) -> uuid.UUID:
    """user + queued な Job 行を1つ作り、job_id を返す。"""
    async with ctx["session_factory"]() as session:
        user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x")
        session.add(user)
        await session.flush()
        job = await JobRepository(session).create(
            user_id=user.id,
            problem_type=problem.problem_type,
            payload={
                "request": SolveRequest(problem=problem).model_dump(mode="json"),
                "result": None,
                "error": None,
            },
        )
        await session.commit()
        return job.id


async def test_solve_job_marks_succeeded_and_stores_result(ctx: dict[str, Any]) -> None:
    problem = build_route_problem(forbidden=["e_bd"], required=["C"])
    job_id = await _make_job(ctx, problem=problem)

    await solve_job(ctx, str(job_id))

    async with ctx["session_factory"]() as session:
        row = await JobRepository(session).get_by_id(job_id)
        assert row is not None
        assert row.status == "succeeded"
        assert row.payload["result"]["status"] == "valid"
        assert row.payload["error"] is None


async def test_solve_job_marks_failed_and_records_error(
    ctx: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    # registry を空にして NoAlgorithmError を誘発し、失敗パスの記録を確認する
    from app.algorithms.registry import REGISTRY

    monkeypatch.setitem(REGISTRY, "route_planning", [])
    job_id = await _make_job(ctx, problem=build_route_problem())

    await solve_job(ctx, str(job_id))

    async with ctx["session_factory"]() as session:
        row = await JobRepository(session).get_by_id(job_id)
        assert row is not None
        assert row.status == "failed"
        assert row.payload["result"] is None
        assert row.payload["error"] is not None


async def test_solve_job_is_a_noop_for_unknown_job_id(ctx: dict[str, Any]) -> None:
    # 通常は起こらない(投入直後に消える等)が、落ちずに静かに戻ることを確認する
    await solve_job(ctx, str(uuid.uuid4()))


def test_worker_settings_max_jobs_reads_from_config() -> None:
    """(Phase 15-5) WorkerSettings.max_jobs が settings.WORKER_MAX_JOBS から来ていること。

    CPU バウンドな solve_job/simulate_job では GIL 競合により同時実行数を増やしても
    真の並列化はされない(実測は Phase-15-5.md)── arq 既定の 10 でなく、env 変数化した
    控えめな値(既定 4)を使う設計を固定する回帰テスト。
    """
    from app.core.config import settings
    from app.worker import WorkerSettings

    assert WorkerSettings.max_jobs == settings.WORKER_MAX_JOBS


async def test_simulate_job_marks_succeeded_and_stores_result(ctx: dict[str, Any]) -> None:
    """`_run_job` の共通化(solve_job / simulate_job)後も simulate の書き戻しが変わらないこと。
    `SimulationRequest` の Job を作り、`simulate_job` が result だけをマージして
    succeeded にする。"""
    from tests.fixtures.optimization import build_project_problem

    from app.schemas.simulation import ScenarioOverride, SimulationRequest
    from app.worker import simulate_job

    request = SimulationRequest(
        problem=build_project_problem(),
        scenarios=[ScenarioOverride(label="tighter", overrides={"data": {"resource_capacity": 1}})],
    )
    async with ctx["session_factory"]() as session:
        user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x")
        session.add(user)
        await session.flush()
        job = await JobRepository(session).create(
            user_id=user.id,
            problem_type=request.problem.problem_type,
            payload={"request": request.model_dump(mode="json"), "result": None, "error": None},
        )
        await session.commit()
        job_id = job.id

    await simulate_job(ctx, str(job_id))

    async with ctx["session_factory"]() as session:
        row = await JobRepository(session).get_by_id(job_id)
        assert row is not None
        assert row.status == "succeeded"
        assert [s["label"] for s in row.payload["result"]["scenarios"]] == ["tighter"]
        assert row.payload["error"] is None


async def test_run_job_hides_internal_error_details_but_keeps_app_error_messages(
    ctx: dict[str, Any],
) -> None:
    """AppError(利用者向けの文言)はそのまま、想定外の例外は固定文言にして内部事情を返さない。"""
    from app.services.errors import NoAlgorithmError
    from app.worker import _run_job

    async def unexpected(_session: Any, _job: Any) -> dict[str, Any]:
        raise RuntimeError("SELECT secret FROM internal_table failed at /srv/app/x.py")

    async def expected(_session: Any, _job: Any) -> dict[str, Any]:
        raise NoAlgorithmError("no algorithm for x")

    job_a = await _make_job(ctx, problem=build_route_problem())
    job_b = await _make_job(ctx, problem=build_route_problem())
    await _run_job(ctx, str(job_a), unexpected)
    await _run_job(ctx, str(job_b), expected)

    async with ctx["session_factory"]() as session:
        a = await JobRepository(session).get_by_id(job_a)
        b = await JobRepository(session).get_by_id(job_b)
        assert a is not None and b is not None
        assert a.payload["error"] == "internal error"
        assert b.payload["error"] == "no algorithm for x"


async def test_run_job_recovers_when_runner_breaks_the_session(ctx: dict[str, Any]) -> None:
    """runner が DB エラー(主キー重複の flush)でセッションを「要 rollback」にしても、
    rollback してから failed を記録できる ── Job が running のまま固着しない(診断書 §5-2)。"""
    from app.worker import _run_job

    job_id = await _make_job(ctx, problem=build_route_problem())

    async def breaks_session(session: Any, job: Any) -> dict[str, Any]:
        session.add(User(id=job.user_id, email="dup@example.com", hashed_password="x"))
        await session.flush()  # 既存ユーザーと主キー衝突 -> IntegrityError
        return {}

    await _run_job(ctx, str(job_id), breaks_session)

    async with ctx["session_factory"]() as session:
        row = await JobRepository(session).get_by_id(job_id)
        assert row is not None
        assert row.status == "failed"
        assert row.payload["error"] == "internal error"
