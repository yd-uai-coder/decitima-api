# DeciTima samples │ Phase 11
"""作業単位 11-7: `ProblemStructuringService`。

テスト対象 / ドライバ / スタブ:
- 対象: `ProblemStructuringService.structure`
- ドライバ: このテスト関数 / `db_session` フィクスチャ(`tests/conftest.py`)
- スタブ: `FakeRedis`(RateLimiter が使う incr/expire だけ)+ `get_structuring_workflow` を
  差し替えたフェイクワークフロー(`ainvoke` が固定結果 or 例外を返すだけ)。Structuring
  ワークフロー自体のノード合成は 11-6 の `test_structuring_workflow.py` で確認済みのため、
  ここでは「サービスがワークフローの結果をどう扱うか(会話記録・リトライ・例外伝播)」だけに
  対象を絞る。
"""

from __future__ import annotations

import uuid
from typing import Any, cast

import pytest
from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from tests.fixtures.fake_redis import FakeRedis

from app.core.config import settings
from app.domain.problems.base_problems import get_base_problem
from app.models.conversation import Message
from app.models.user import User
from app.services.errors import (
    ConversationNotFoundError,
    GenerationFailedError,
    ProblemValidationError,
    RateLimitExceededError,
)
from app.services.structuring import ProblemStructuringService


class _FakeWorkflow:
    """`get_structuring_workflow()` の代替。`ainvoke` が固定結果 or 例外を返すだけ。"""

    def __init__(self, results: list[Any]) -> None:
        # results: 呼ばれるたびに1つずつ消費する。dict は成功として返し、
        # Exception のインスタンスは送出する。
        self._results = list(results)
        self.call_count = 0

    async def ainvoke(self, _state: dict) -> dict:
        self.call_count += 1
        result = self._results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _patch_workflow(monkeypatch: pytest.MonkeyPatch, workflow: _FakeWorkflow) -> None:
    monkeypatch.setattr("app.ai.graph.workflow.get_structuring_workflow", lambda: workflow)


def _success_result(problem_type: str = "route_planning") -> dict:
    return {
        "problem": get_base_problem(problem_type),
        "problem_type": problem_type,
        "notes": [],
    }


def _service(session: AsyncSession) -> ProblemStructuringService:
    return ProblemStructuringService(session, cast(Redis, FakeRedis()))


async def _make_user(session: AsyncSession) -> User:
    user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x")
    session.add(user)
    await session.flush()
    return user


async def test_structure_creates_a_new_conversation_and_records_both_messages(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_workflow(monkeypatch, _FakeWorkflow([_success_result("travel_planning")]))
    user = await _make_user(db_session)

    conversation, problem = await _service(db_session).structure(
        user_id=user.id, conversation_id=None, text="5万円以内で東京を2日間旅行したい"
    )

    assert problem.problem_type == "travel_planning"
    messages = (
        (
            await db_session.execute(
                select(Message).where(Message.conversation_id == conversation.id)
            )
        )
        .scalars()
        .all()
    )
    assert [m.role for m in messages] == ["user", "assistant"]
    assert messages[0].content == "5万円以内で東京を2日間旅行したい"


async def test_structure_reuses_an_existing_conversation(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_workflow(
        monkeypatch,
        _FakeWorkflow([_success_result("route_planning"), _success_result("route_planning")]),
    )
    user = await _make_user(db_session)
    service = _service(db_session)

    first, _ = await service.structure(user_id=user.id, conversation_id=None, text="1回目")
    second, _ = await service.structure(user_id=user.id, conversation_id=first.id, text="2回目")

    assert first.id == second.id
    messages = (
        (await db_session.execute(select(Message).where(Message.conversation_id == first.id)))
        .scalars()
        .all()
    )
    assert len(messages) == 4  # user/assistant が2往復


async def test_structure_raises_conversation_not_found_for_an_unknown_id(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _patch_workflow(monkeypatch, _FakeWorkflow([_success_result()]))
    user = await _make_user(db_session)

    with pytest.raises(ConversationNotFoundError):
        await _service(db_session).structure(
            user_id=user.id, conversation_id=uuid.uuid4(), text="dummy"
        )


async def test_structure_propagates_validation_errors_without_retrying(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Validation/グラウンディング失敗は入力起因でリトライしても解消しないため、
    即座に伝播しリトライされない(呼び出しは1回だけ)。"""
    workflow = _FakeWorkflow([ProblemValidationError("bad reference")])
    _patch_workflow(monkeypatch, workflow)
    user = await _make_user(db_session)

    with pytest.raises(ProblemValidationError):
        await _service(db_session).structure(user_id=user.id, conversation_id=None, text="dummy")
    assert workflow.call_count == 1


async def test_structure_retries_transient_errors_then_succeeds(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.services.structuring.asyncio.sleep", _no_sleep)
    workflow = _FakeWorkflow([RuntimeError("transient"), _success_result()])
    _patch_workflow(monkeypatch, workflow)
    user = await _make_user(db_session)

    _, problem = await _service(db_session).structure(
        user_id=user.id, conversation_id=None, text="dummy"
    )

    assert problem.problem_type == "route_planning"
    assert workflow.call_count == 2


async def test_structure_gives_up_after_max_attempts(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("app.services.structuring.asyncio.sleep", _no_sleep)
    workflow = _FakeWorkflow([RuntimeError("1"), RuntimeError("2"), RuntimeError("3")])
    _patch_workflow(monkeypatch, workflow)
    user = await _make_user(db_session)

    with pytest.raises(GenerationFailedError):
        await _service(db_session).structure(user_id=user.id, conversation_id=None, text="dummy")
    assert workflow.call_count == 3


async def test_structure_enforces_its_own_rate_limit(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "STRUCTURE_RATE_LIMIT_PER_HOUR", 1)
    _patch_workflow(monkeypatch, _FakeWorkflow([_success_result(), _success_result()]))
    user = await _make_user(db_session)
    service = _service(db_session)

    await service.structure(user_id=user.id, conversation_id=None, text="1回目")
    with pytest.raises(RateLimitExceededError):
        await service.structure(user_id=user.id, conversation_id=None, text="2回目")


async def test_structure_bypasses_rate_limit_when_requested(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "STRUCTURE_RATE_LIMIT_PER_HOUR", 1)
    _patch_workflow(monkeypatch, _FakeWorkflow([_success_result(), _success_result()]))
    user = await _make_user(db_session)
    service = _service(db_session)

    await service.structure(
        user_id=user.id, conversation_id=None, text="1回目", bypass_rate_limit=True
    )
    await service.structure(
        user_id=user.id, conversation_id=None, text="2回目", bypass_rate_limit=True
    )
