"""作業単位 1-6: SolveService のライフサイクル(db_session + FakeRedis)。"""

import uuid
from typing import cast

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from tests.fixtures.fake_redis import FakeRedis
from tests.fixtures.optimization import build_route_problem, build_shift_problem

from app.domain.solutions.route_planner import RouteSolution
from app.models.user import User
from app.schemas.optimization import SolveRequest
from app.services.errors import (
    InfeasibleProblemError,
    NoAlgorithmError,
    SolveTimeoutError,
)
from app.services.solve import SolveService


def _service(session: AsyncSession) -> SolveService:
    # FakeRedis は RateLimiter が使う incr / expire だけを模した代替(型は Redis として渡す)
    return SolveService(session, cast(Redis, FakeRedis()))


async def _make_user(session: AsyncSession) -> User:
    user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x")
    session.add(user)
    await session.flush()
    return user


async def test_solve_persists_problem_and_verified_solution(
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session)

    outcome = await _service(db_session).solve(
        user_id=user.id,
        request=SolveRequest(problem=build_route_problem(forbidden=["e_bd"], required=["C"])),
    )

    assert outcome.solution.status == "valid"
    assert isinstance(outcome.solution.assignments, RouteSolution)
    assert outcome.solution.assignments.total_weight == 9.0
    assert outcome.problem_id is not None
    assert outcome.solution_id is not None
    assert outcome.solution.problem_ref == outcome.problem_id


async def test_persist_false_returns_no_ids(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    outcome = await _service(db_session).solve(
        user_id=user.id,
        request=SolveRequest(problem=build_route_problem(), persist=False),
    )
    assert outcome.problem_id is None
    assert outcome.solution_id is None


async def test_infeasible_problem_raises_before_solving(
    db_session: AsyncSession,
) -> None:
    user = await _make_user(db_session)
    with pytest.raises(InfeasibleProblemError):
        await _service(db_session).solve(
            user_id=user.id,
            request=SolveRequest(problem=build_route_problem(forbidden=["e_ce", "e_de"])),
        )

# shift_schedulingを用意したのでNoAlgorithmErrorは出ない->テストを無効化する
# async def test_unsupported_problem_type_raises_no_algorithm(
#     db_session: AsyncSession,
# ) -> None:
#     user = await _make_user(db_session)
#     with pytest.raises(NoAlgorithmError):
#         await _service(db_session).solve(
#             user_id=user.id, request=SolveRequest(problem=build_shift_problem())
#         )

async def test_no_algorithm_for_problem_type_raises(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Phase 6 で shift にも strategy が付いたので、registry キーを空にして「候補ゼロ」を再現する
    from app.algorithms.registry import REGISTRY

    monkeypatch.setitem(REGISTRY, "shift_scheduling", [])
    user = await _make_user(db_session)
    with pytest.raises(NoAlgorithmError):
        await _service(db_session).solve(
            user_id=user.id, request=SolveRequest(problem=build_shift_problem())
        )


async def test_timeout_raises_solve_timeout_error(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    import time

    from app.algorithms.graph.dijkstra import DijkstraStrategy

    # solve をわざと遅くして、timeout_seconds を極小にする
    def _slow_solve(self: DijkstraStrategy, problem):  # noqa: ANN001, ANN202
        time.sleep(0.2)
        raise AssertionError("should have timed out")

    monkeypatch.setattr(DijkstraStrategy, "solve", _slow_solve)
    user = await _make_user(db_session)
    with pytest.raises(SolveTimeoutError):
        await _service(db_session).solve(
            user_id=user.id,
            request=SolveRequest(problem=build_route_problem(), timeout_seconds=0.01),
        )
