"""作業単位 13-2: `SolutionExplanationService`。

テスト対象 / ドライバ / スタブ:
- 対象: `SolutionExplanationService.explain`
- ドライバ: このテスト関数
- スタブ: `FakeRedis`(RateLimiter が使う incr/expire だけ)+ `FakeLLM`
  (`app.services.explanation.get_gemini_llm` を差し替える ── Phase 12 と同じ「呼び出し元
  モジュールの名前空間を monkeypatch する」形)。永続化済みの Problem/Solution は
  `SolveService.solve`(Phase 1、無変更)で実際に1件作る ── フェイクの CandidateSolution を
  手組みするより、実データで説明サービスを検証できる。
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
from app.services.errors import NotFoundError, RateLimitExceededError
from app.services.explanation import SolutionExplanationService
from app.services.solve import SolveService


async def _make_user(session: AsyncSession) -> User:
    user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x")
    session.add(user)
    await session.flush()
    return user


async def _seed_solution(session: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    """既存 SolveService(Phase 1、無変更)で実際に Problem/Solution を1件永続化する。"""
    outcome = await SolveService(session, cast(Redis, FakeRedis())).solve(
        user_id=user_id,
        request=SolveRequest(problem=build_route_problem(forbidden=["e_bd"], required=["C"])),
    )
    assert outcome.solution_id is not None
    return outcome.solution_id


def _service(session: AsyncSession) -> SolutionExplanationService:
    return SolutionExplanationService(session, cast(Redis, FakeRedis()))


def _patch_llm(monkeypatch: pytest.MonkeyPatch, structured: LlmExplanation) -> None:
    monkeypatch.setattr(explanation, "get_gemini_llm", lambda **_: FakeLLM(structured=structured))


async def test_explain_returns_llm_narrative(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await _make_user(db_session)
    solution_id = await _seed_solution(db_session, user.id)
    _patch_llm(
        monkeypatch,
        LlmExplanation(
            why_this_solution="制約を満たしつつ最短経路を選びました",
            key_constraints="C を必ず経由する制約が効いています",
            algorithm_rationale="非負辺なので dijkstra を使いました",
            alternatives_comparison="bellman_ford は負辺対応ですが今回は不要です",
            improvement_notes="改善余地はありません",
        ),
    )

    result = await _service(db_session).explain(solution_id, user_id=user.id)

    assert result.solution_id == solution_id
    assert result.problem_type == "route_planning"
    assert result.algorithm_name == "dijkstra"
    assert "最短経路" in result.why_this_solution
    assert result.notes == []


async def test_explain_falls_back_when_llm_fails(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user = await _make_user(db_session)
    solution_id = await _seed_solution(db_session, user.id)

    class _BoomLLM:
        def with_structured_output(self, _schema: object) -> _BoomLLM:
            return self

        async def ainvoke(self, _messages: object) -> None:
            raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(explanation, "get_gemini_llm", lambda **_: _BoomLLM())

    result = await _service(db_session).explain(solution_id, user_id=user.id)

    assert result.algorithm_name == "dijkstra"
    assert "total_weight" in result.why_this_solution
    assert "LLM 説明生成に失敗した" in result.notes[0]


async def test_explain_unknown_solution_raises_not_found(db_session: AsyncSession) -> None:
    user = await _make_user(db_session)
    with pytest.raises(NotFoundError):
        await _service(db_session).explain(uuid.uuid4(), user_id=user.id)


async def test_explain_enforces_its_own_rate_limit(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(explanation.settings, "EXPLAIN_RATE_LIMIT_PER_HOUR", 1)
    user = await _make_user(db_session)
    solution_id = await _seed_solution(db_session, user.id)
    _patch_llm(
        monkeypatch,
        LlmExplanation(
            why_this_solution="x",
            key_constraints="x",
            algorithm_rationale="x",
            alternatives_comparison="x",
            improvement_notes="x",
        ),
    )
    # キャッシュに当たらない別の解で 2 回呼ぶ(同じ解の 2 回目はキャッシュヒットで枠を消費しない)
    other_solution_id = await _seed_solution(db_session, user.id)
    service = _service(db_session)

    await service.explain(solution_id, user_id=user.id)
    with pytest.raises(RateLimitExceededError):
        await service.explain(other_solution_id, user_id=user.id)


async def test_explain_bypasses_rate_limit_when_requested(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(explanation.settings, "EXPLAIN_RATE_LIMIT_PER_HOUR", 1)
    user = await _make_user(db_session)
    solution_id = await _seed_solution(db_session, user.id)
    _patch_llm(
        monkeypatch,
        LlmExplanation(
            why_this_solution="x",
            key_constraints="x",
            algorithm_rationale="x",
            alternatives_comparison="x",
            improvement_notes="x",
        ),
    )
    service = _service(db_session)

    for _ in range(3):
        await service.explain(solution_id, user_id=user.id, bypass_rate_limit=True)
