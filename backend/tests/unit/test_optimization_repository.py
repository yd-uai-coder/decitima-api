"""作業単位 1-5: Problem / Solution リポジトリ(db_session = インメモリ SQLite)。
JSONB 固有の挙動(Postgres 上での部分検索など)の確認は tests/integration/ 側。
"""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession
from tests.fixtures.optimization import build_route_problem

from app.models.user import User
from app.repositories.optimization import ProblemRepository, SolutionRepository


async def _seed_user(session: AsyncSession) -> User:
    user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x")
    session.add(user)
    await session.flush()
    return user


async def test_problem_and_solution_roundtrip(db_session: AsyncSession) -> None:
    user = await _seed_user(db_session)
    problem = build_route_problem(forbidden=["e_bd"], required=["C"])

    prow = await ProblemRepository(db_session).create(
        user_id=user.id,
        problem_type=problem.problem_type,
        payload=problem.model_dump(mode="json"),
    )
    srow = await SolutionRepository(db_session).create(
        problem_id=prow.id,
        status="valid",
        algorithm_name="dijkstra",
        algorithm_implementation="handwritten",
        payload={"status": "valid", "metrics": {"total_weight": 9.0}},
    )
    await db_session.commit()

    fetched = await SolutionRepository(db_session).get_by_id(srow.id)
    assert fetched is not None
    assert fetched.problem_id == prow.id
    assert fetched.payload["metrics"]["total_weight"] == 9.0


async def test_json_column_updated_by_whole_reassignment(
    db_session: AsyncSession,
) -> None:
    # JSON は中身を書き換えず「まるごと代入」で更新する(ミューテーション追跡の落とし穴回避)
    user = await _seed_user(db_session)
    prow = await ProblemRepository(db_session).create(
        user_id=user.id, problem_type="route_planning", payload={"v": 1}
    )
    await db_session.commit()

    prow.payload = {**prow.payload, "v": 2}
    await db_session.commit()

    again = await ProblemRepository(db_session).get_by_id(prow.id)
    assert again is not None
    assert again.payload["v"] == 2


async def test_list_for_problem_orders_by_created_at(db_session: AsyncSession) -> None:
    user = await _seed_user(db_session)
    prow = await ProblemRepository(db_session).create(
        user_id=user.id,
        problem_type="route_planning",
        payload=build_route_problem().model_dump(mode="json"),
    )
    for name in ("dijkstra", "a_star"):
        await SolutionRepository(db_session).create(
            problem_id=prow.id,
            status="valid",
            algorithm_name=name,
            algorithm_implementation="handwritten",
            payload={},
        )
    await db_session.commit()

    rows = await SolutionRepository(db_session).list_for_problem(prow.id)
    assert [r.algorithm_name for r in rows] == ["dijkstra", "a_star"]
