# DeciTima samples │ 作業単位 15-6
"""`SolutionExplanationService` の Redis キャッシュ(Phase 15-6)。

テスト対象 / ドライバ / スタブ:
- 対象: `SolutionExplanationService.explain` のキャッシュ経路(2回目呼び出しでLLMを呼ばない、
  失敗時はキャッシュしない、キャッシュヒットでも所有者チェックは必ず先に通る)
- ドライバ: このテスト関数
- スタブ: `FakeRedis`(Phase 15-6 で get/set 対応。`test_explanation_service.py` と違い、
  ここでは同一インスタンスを2回の `explain()` 呼び出しで**共有**する ── キャッシュの
  ヒット/ミスを観測するにはインスタンスを跨いで状態を持ち越す必要があるため)+ `FakeLLM`
  (`structured_sequence` を1件だけ渡し、2回目に本当に LLM へ到達すると `IndexError` から
  フォールバック応答に落ちる ── 応答内容の比較でLLM再呼び出しの有無を検証できる)。
"""

from __future__ import annotations

import uuid
from typing import cast

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from tests.fixtures.fake_llm import FakeLLM
from tests.fixtures.fake_redis import FakeRedis
from tests.fixtures.optimization import build_route_problem

from app.models.user import User
from app.schemas.explanation import LlmExplanation
from app.schemas.optimization import SolveRequest
from app.services import explanation
from app.services.errors import NotFoundError
from app.services.explanation import SolutionExplanationService
from app.services.solve import SolveService


async def _make_user(session: AsyncSession) -> User:
    user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x")
    session.add(user)
    await session.flush()
    return user


async def _seed_solution(session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    outcome = await SolveService(session, cast(Redis, FakeRedis())).solve(
        user_id=user_id,
        request=SolveRequest(problem=build_route_problem(forbidden=["e_bd"], required=["C"])),
    )
    assert outcome.solution_id is not None
    return outcome.solution_id


_EXPLANATION = LlmExplanation(
    why_this_solution="制約を満たしつつ最短距離です",
    key_constraints="e_bd を通らない、Cを必ず含む",
    algorithm_rationale="Dijkstra は非負辺の最短経路に最適",
    alternatives_comparison="他候補との違いはありません",
    improvement_notes="特にありません",
)


async def test_second_call_hits_cache_and_skips_llm(db_session: AsyncSession, monkeypatch) -> None:
    user = await _make_user(db_session)
    solution_id = await _seed_solution(db_session, user.id)

    # structured_sequence を1件だけ渡す ── 2回目に本当にLLMへ到達すると IndexError になり
    # フォールバック応答(固定文言)に落ちるので、応答内容の一致でキャッシュヒットを検証できる
    monkeypatch.setattr(
        explanation,
        "get_gemini_llm",
        lambda **_: FakeLLM(structured_sequence=[_EXPLANATION]),
    )

    shared_redis = cast(Redis, FakeRedis())  # 2回の explain() で同じ Redis を共有する
    service = SolutionExplanationService(db_session, shared_redis)

    first = await service.explain(solution_id, user_id=user.id, bypass_rate_limit=True)
    second = await service.explain(solution_id, user_id=user.id, bypass_rate_limit=True)

    assert first.why_this_solution == _EXPLANATION.why_this_solution
    assert second == first  # 2回目もLLM由来の応答と同一(フォールバックに落ちていない)


async def test_llm_failure_is_not_cached(db_session: AsyncSession, monkeypatch) -> None:
    user = await _make_user(db_session)
    solution_id = await _seed_solution(db_session, user.id)

    monkeypatch.setattr(
        explanation,
        "get_gemini_llm",
        lambda **_: FakeLLM(structured_sequence=[RuntimeError("gemini down")]),
    )

    shared_redis = cast(Redis, FakeRedis())
    service = SolutionExplanationService(db_session, shared_redis)

    response = await service.explain(solution_id, user_id=user.id, bypass_rate_limit=True)

    assert response.notes == ["LLM 説明生成に失敗したため、機械的な要約のみ返しています"]
    cached = await shared_redis.get(f"explain:{solution_id}")
    assert cached is None  # フォールバック応答はキャッシュされない


async def test_cache_hit_still_enforces_owner_scope(db_session: AsyncSession, monkeypatch) -> None:
    owner = await _make_user(db_session)
    other = await _make_user(db_session)
    solution_id = await _seed_solution(db_session, owner.id)

    monkeypatch.setattr(
        explanation,
        "get_gemini_llm",
        lambda **_: FakeLLM(structured_sequence=[_EXPLANATION]),
    )

    shared_redis = cast(Redis, FakeRedis())
    service = SolutionExplanationService(db_session, shared_redis)
    # キャッシュに載せる
    await service.explain(solution_id, user_id=owner.id, bypass_rate_limit=True)

    with pytest.raises(NotFoundError):
        await service.explain(solution_id, user_id=other.id, bypass_rate_limit=True)
