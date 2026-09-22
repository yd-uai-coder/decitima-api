"""作業単位 9-8: JobService(投入側)。
作業単位 10-4: `enqueue_simulation` を追加。

テスト対象 / ドライバ / スタブ:
- 対象: `JobService.enqueue` / `get_status` / `get_for_user`(所有者スコープ・エンキュー失敗の補償)
- ドライバ: このテスト関数 / `db_session` フィクスチャ(Phase 1 の `tests/unit/conftest.py`)
- スタブ: `FakeRedis`(RateLimiter が使う incr/expire だけ)+ フェイク arq プール
  (`enqueue_job` の呼び出し引数だけ記録し、実際には Redis へ繋がない)。**Phase 9 で唯一
  スタブが要る章** ── 対象が外部プロセス(ワーカー)への「投入」という副作用を持つため
  (進行のルール #14「スタブの要否がレイヤー設計の鏡」)。実際にワーカーが拾って処理するかは
  integration テスト(`-m integration`)の領分。
"""

from __future__ import annotations

import uuid
from typing import cast

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from tests.fixtures.fake_redis import FakeRedis
from tests.fixtures.optimization import build_project_problem, build_route_problem

from app.models.user import User
from app.repositories.job import JobRepository
from app.schemas.optimization import SolveRequest
from app.schemas.simulation import ScenarioOverride, SimulationRequest
from app.services.errors import InfeasibleProblemError, NotFoundError
from app.services.job import JobService


class _FakeArqPool:
    """`arq.create_pool` の代替。呼ばれた (function, args, kwargs) を記録するだけ。"""

    def __init__(self) -> None:
        self.enqueued: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    async def enqueue_job(self, function: str, *args: object, **kwargs: object) -> None:
        self.enqueued.append((function, args, kwargs))

    async def aclose(self) -> None:
        pass


def _patch_create_pool(monkeypatch: pytest.MonkeyPatch, pool: _FakeArqPool) -> None:
    async def _fake_create_pool(*_args: object, **_kwargs: object) -> _FakeArqPool:
        return pool

    monkeypatch.setattr("app.services.job.create_pool", _fake_create_pool)


def _service(session: AsyncSession) -> JobService:
    return JobService(session, cast(Redis, FakeRedis()))


async def _make_user(session: AsyncSession) -> User:
    user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x")
    session.add(user)
    await session.flush()
    return user


async def test_enqueue_creates_queued_job_and_submits_to_arq(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_pool = _FakeArqPool()
    _patch_create_pool(monkeypatch, fake_pool)

    user = await _make_user(db_session)
    job = await _service(db_session).enqueue(
        user_id=user.id, request=SolveRequest(problem=build_route_problem())
    )

    assert job.status == "queued"
    assert job.problem_type == "route_planning"
    assert job.payload["result"] is None
    assert fake_pool.enqueued == [("solve_job", (str(job.id),), {"_job_id": str(job.id)})]


async def test_enqueue_rejects_infeasible_problem_before_queueing(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_pool = _FakeArqPool()
    _patch_create_pool(monkeypatch, fake_pool)

    user = await _make_user(db_session)
    with pytest.raises(InfeasibleProblemError):
        await _service(db_session).enqueue(
            user_id=user.id,
            request=SolveRequest(problem=build_route_problem(forbidden=["e_ce", "e_de"])),
        )
    assert fake_pool.enqueued == []  # Validation で弾かれ、キューには積まれない(9-8 の設計方針)


async def test_get_status_returns_none_for_unknown_job(db_session: AsyncSession) -> None:
    assert await _service(db_session).get_status(uuid.uuid4()) is None


async def test_get_status_returns_the_created_job(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_create_pool(monkeypatch, _FakeArqPool())
    user = await _make_user(db_session)
    created = await _service(db_session).enqueue(
        user_id=user.id, request=SolveRequest(problem=build_route_problem())
    )
    fetched = await _service(db_session).get_status(created.id)
    assert fetched is not None
    assert fetched.id == created.id
    assert fetched.status == "queued"


# --- 作業単位 10-4: enqueue_simulation ---------------------------------------------------


async def test_enqueue_simulation_creates_queued_job_and_submits_to_arq(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_pool = _FakeArqPool()
    _patch_create_pool(monkeypatch, fake_pool)

    user = await _make_user(db_session)
    request = SimulationRequest(
        problem=build_project_problem(),
        scenarios=[ScenarioOverride(label="tighter", overrides={"data": {"resource_capacity": 1}})],
    )
    job = await _service(db_session).enqueue_simulation(user_id=user.id, request=request)

    assert job.status == "queued"
    assert job.problem_type == "project_scheduling"
    assert job.payload["result"] is None
    assert fake_pool.enqueued == [("simulate_job", (str(job.id),), {"_job_id": str(job.id)})]


async def test_enqueue_simulation_rejects_infeasible_base_problem_before_queueing(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """base problem だけ Validation する ── 明らかに無理な base は投入前に弾く
    (各シナリオの検証はワーカー側の `run_simulation` が実行時に行う)。"""
    fake_pool = _FakeArqPool()
    _patch_create_pool(monkeypatch, fake_pool)

    user = await _make_user(db_session)
    request = SimulationRequest(
        problem=build_route_problem(forbidden=["e_ce", "e_de"]),
        scenarios=[ScenarioOverride(label="noop", overrides={})],
    )
    with pytest.raises(InfeasibleProblemError):
        await _service(db_session).enqueue_simulation(user_id=user.id, request=request)
    assert fake_pool.enqueued == []


async def test_enqueue_simulation_uses_a_separate_rate_limit_from_solve_jobs(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """simulate_submit は job_submit と別枠 ── solve ジョブを1件積んだ直後でも
    simulate ジョブの投入はブロックされない。"""
    _patch_create_pool(monkeypatch, _FakeArqPool())
    user = await _make_user(db_session)
    service = _service(db_session)

    await service.enqueue(user_id=user.id, request=SolveRequest(problem=build_route_problem()))
    job = await service.enqueue_simulation(
        user_id=user.id,
        request=SimulationRequest(
            problem=build_route_problem(),
            scenarios=[ScenarioOverride(label="noop", overrides={})],
        ),
    )
    assert job.status == "queued"


# --- 所有者スコープ(get_for_user)/ エンキュー失敗の補償 -------------------------------------


async def test_get_for_user_returns_own_job(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_create_pool(monkeypatch, _FakeArqPool())
    user = await _make_user(db_session)
    created = await _service(db_session).enqueue(
        user_id=user.id, request=SolveRequest(problem=build_route_problem())
    )
    fetched = await _service(db_session).get_for_user(created.id, user_id=user.id)
    assert fetched.id == created.id


async def test_get_for_user_hides_other_users_job_as_not_found(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """他人のジョブは「存在しない」と区別できない NotFoundError(id の存在有無を漏らさない)。
    superuser だけは読める。"""
    _patch_create_pool(monkeypatch, _FakeArqPool())
    owner = await _make_user(db_session)
    other = await _make_user(db_session)
    created = await _service(db_session).enqueue(
        user_id=owner.id, request=SolveRequest(problem=build_route_problem())
    )

    with pytest.raises(NotFoundError):
        await _service(db_session).get_for_user(created.id, user_id=other.id)
    with pytest.raises(NotFoundError):
        await _service(db_session).get_for_user(uuid.uuid4(), user_id=owner.id)

    as_admin = await _service(db_session).get_for_user(
        created.id, user_id=other.id, is_superuser=True
    )
    assert as_admin.id == created.id


async def test_enqueue_marks_job_failed_when_arq_submission_fails(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """commit 済みの Job が queued のまま孤児にならない ── failed に倒して例外を伝播する。"""

    async def _broken_create_pool(*_args: object, **_kwargs: object) -> _FakeArqPool:
        raise ConnectionError("redis down")

    monkeypatch.setattr("app.services.job.create_pool", _broken_create_pool)
    user = await _make_user(db_session)
    service = _service(db_session)

    with pytest.raises(ConnectionError):
        await service.enqueue(user_id=user.id, request=SolveRequest(problem=build_route_problem()))

    jobs = await JobRepository(db_session).list_all(user_id=user.id)
    assert [j.status for j in jobs] == ["failed"]
    assert jobs[0].payload["error"] == "failed to enqueue job"  # 内部例外の文言は返さない
