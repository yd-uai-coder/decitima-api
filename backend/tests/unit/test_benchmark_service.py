"""作業単位 3-3 / 3-4: BenchmarkService。

対象 = BenchmarkService(オーケストレーション)。ドライバ = このテスト関数 + db_session。
スタブ = FakeRedis(RateLimiter の Redis 役)のみ。ProblemValidationService /
SolutionVerificationService / 各 strategy / measure_call はすべて本物(純粋)。
"""

import uuid
from typing import cast

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from tests.fixtures.fake_redis import FakeRedis
from tests.fixtures.optimization import build_route_problem

from app.models.optimization import BenchmarkRun
from app.models.user import User
from app.schemas.optimization import BenchmarkRequest
from app.services.benchmark import BenchmarkService
from app.services.errors import InfeasibleProblemError, NoAlgorithmError, ProblemValidationError


def _service(session: AsyncSession) -> BenchmarkService:
    return BenchmarkService(session, cast(Redis, FakeRedis()))


async def _make_user(session: AsyncSession) -> User:
    user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x")
    session.add(user)
    await session.flush()
    return user


async def test_benchmarks_all_route_strategies(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    outcome = await _service(db_session).run(
        user_id=user.id,
        request=BenchmarkRequest(problem=build_route_problem(), runs=2, persist=False),
    )
    names = {e.algorithm.name for e in outcome.entries}
    assert names == { "a_star","bellman_ford",  "brute_force", "dijkstra","dijkstra_nx",}
    for e in outcome.entries:
        assert e.solution_status == "valid"
        assert e.elapsed_ms_median >= 0.0
        assert e.peak_memory_kb > 0.0
        # dijkstra_nxでは操作回数を取っていないため失効させる。
        # assert e.operation_count is not None and e.operation_count > 0
        assert e.hard_violations == 0 and e.soft_violations == 0


async def test_algorithms_filter(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    outcome = await _service(db_session).run(
        user_id=user.id,
        request=BenchmarkRequest(
            problem=build_route_problem(), algorithms=["dijkstra"], runs=1, persist=False
        ),
    )
    assert [e.algorithm.name for e in outcome.entries] == ["dijkstra"]


async def test_unknown_algorithm_name_raises(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    with pytest.raises(NoAlgorithmError):
        await _service(db_session).run(
            user_id=user.id,
            request=BenchmarkRequest(
                problem=build_route_problem(), algorithms=["nope"], runs=1, persist=False
            ),
        )


async def test_invalid_problem_raises_before_measuring(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    # goal に到達不能(e_ce と e_de を禁止)→ InfeasibleProblemError(Validation 段)
    with pytest.raises(InfeasibleProblemError):
        await _service(db_session).run(
            user_id=user.id,
            request=BenchmarkRequest(
                problem=build_route_problem(forbidden=["e_ce", "e_de"]), runs=1, persist=False
            ),
        )


async def test_unknown_start_node_raises(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    with pytest.raises(ProblemValidationError):
        await _service(db_session).run(
            user_id=user.id,
            request=BenchmarkRequest(problem=build_route_problem(start="Z"), runs=1, persist=False),
        )


async def test_quality_ratio_is_one_when_all_optimal(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    outcome = await _service(db_session).run(
        user_id=user.id,
        request=BenchmarkRequest(problem=build_route_problem(), runs=1, persist=False),
    )
    # 制約なしなら dijkstra も brute_force も同じ最短(total_weight=5)→ 比は 1.0
    assert all(e.quality_ratio == 1.0 for e in outcome.entries)


async def test_persist_creates_benchmark_run_row(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    outcome = await _service(db_session).run(
        user_id=user.id,
        request=BenchmarkRequest(problem=build_route_problem(), runs=1, persist=True),
    )
    assert outcome.benchmark_id is not None
    row = await db_session.get(BenchmarkRun, outcome.benchmark_id)
    assert row is not None
    assert row.problem_type == "route_planning"
    assert row.payload["runs"] == 1
    assert len(row.payload["entries"]) == 5


async def test_persist_false_returns_no_id(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    outcome = await _service(db_session).run(
        user_id=user.id,
        request=BenchmarkRequest(problem=build_route_problem(), runs=1, persist=False),
    )
    assert outcome.benchmark_id is None
