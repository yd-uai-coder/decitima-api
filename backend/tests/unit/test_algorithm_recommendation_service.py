# DeciTima samples │ 初出 Phase 12
"""作業単位 12-2: `AlgorithmRecommendationService`。

テスト対象 / ドライバ / スタブ:
- 対象: `AlgorithmRecommendationService.recommend`
- ドライバ: このテスト関数
- スタブ: `FakeRedis`(RateLimiter が使う incr/expire だけ)+ `FakeLLM`
  (`app.services.algorithm_recommendation.get_gemini_llm` を差し替える ── 11-3 の
  `test_ai_graph_nodes.py` と同じ「呼び出し元モジュールの名前空間を monkeypatch する」形)。
  `select_strategy`/`get_strategies` は本物(純粋・DB非依存なのでスタブ不要)。
"""

from __future__ import annotations

import uuid
from typing import cast

import pytest
from redis.asyncio import Redis
from tests.fixtures.fake_llm import FakeLLM
from tests.fixtures.fake_redis import FakeRedis
from tests.fixtures.optimization import build_travel_problem

from app.schemas.recommendation import LlmAlgorithmComment, LlmRecommendation
from app.services import algorithm_recommendation
from app.services.algorithm_recommendation import AlgorithmRecommendationService
from app.services.errors import RateLimitExceededError


def _service() -> AlgorithmRecommendationService:
    return AlgorithmRecommendationService(cast(Redis, FakeRedis()))


def _patch_llm(monkeypatch: pytest.MonkeyPatch, structured: LlmRecommendation) -> None:
    monkeypatch.setattr(
        algorithm_recommendation,
        "get_gemini_llm",
        lambda **_: FakeLLM(structured=structured),
    )


# (Phase 12)
async def test_recommend_skips_llm_when_only_one_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """候補が1件しかない状況を作為的に再現する(現行 registry には無いが、将来の
    problem_type 追加初期でも起こり得るため、機構としてテストする ── rule #15 の
    「集約の機構のテストはフェイクで」に準じ、候補リストだけを差し替える)。"""
    from app.algorithms.registry import get_strategies as real_get_strategies

    only = real_get_strategies("travel_planning")[:1]  # knapsack_dp のみに絞る
    monkeypatch.setattr(algorithm_recommendation, "get_strategies", lambda _pt: only)

    result = await _service().recommend(user_id=uuid.uuid4(), problem=build_travel_problem())

    assert [r.name for r in result.recommendations] == ["knapsack_dp"]
    assert result.recommendations[0].is_rule_preferred is True
    assert result.recommendations[0].llm_rank is None
    assert "LLM は呼び出していません" in result.notes[0]


async def test_recommend_merges_rule_and_llm_and_sorts_by_llm_rank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_llm(
        monkeypatch,
        LlmRecommendation(
            ranked_names=["greedy", "knapsack_dp"],
            comments=[
                LlmAlgorithmComment(name="greedy", comment="必ず予算内に収まるので安全"),
                LlmAlgorithmComment(name="knapsack_dp", comment="厳密解だが移動費用を無視"),
            ],
        ),
    )

    result = await _service().recommend(user_id=uuid.uuid4(), problem=build_travel_problem())

    assert result.rule_preferred == "knapsack_dp"
    names_in_order = [r.name for r in result.recommendations]
    # LLM がランク付けした2件(greedy→1位, knapsack_dp→2位)が先頭、
    # ランクの付かなかった brute_force は末尾に残る
    assert names_in_order == ["greedy", "knapsack_dp", "brute_force"]
    knapsack = next(r for r in result.recommendations if r.name == "knapsack_dp")
    assert knapsack.is_rule_preferred is True
    assert knapsack.llm_rank == 2
    greedy = next(r for r in result.recommendations if r.name == "greedy")
    assert greedy.is_rule_preferred is False
    assert greedy.llm_comment == "必ず予算内に収まるので安全"
    assert result.notes == []


async def test_recommend_drops_unknown_llm_names_and_notes_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_llm(
        monkeypatch,
        LlmRecommendation(
            ranked_names=["greedy", "dijkstra"],  # dijkstra は travel_planning に存在しない
            comments=[LlmAlgorithmComment(name="dijkstra", comment="存在しない候補")],
        ),
    )

    result = await _service().recommend(user_id=uuid.uuid4(), problem=build_travel_problem())

    assert all(r.name != "dijkstra" for r in result.recommendations)
    assert any("dijkstra" in note for note in result.notes)


async def test_recommend_falls_back_to_rule_only_when_llm_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BoomLLM:
        def with_structured_output(self, _schema: object) -> _BoomLLM:
            return self

        async def ainvoke(self, _messages: object) -> None:
            raise RuntimeError("LLM unavailable")

    monkeypatch.setattr(algorithm_recommendation, "get_gemini_llm", lambda **_: _BoomLLM())

    result = await _service().recommend(user_id=uuid.uuid4(), problem=build_travel_problem())

    assert {r.name for r in result.recommendations} == {"knapsack_dp", "greedy", "brute_force"}
    assert all(r.llm_rank is None for r in result.recommendations)
    assert "LLM 推薦の呼び出しに失敗した" in result.notes[0]


async def test_recommend_enforces_its_own_rate_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(algorithm_recommendation.settings, "RECOMMEND_RATE_LIMIT_PER_HOUR", 1)
    _patch_llm(monkeypatch, LlmRecommendation(ranked_names=[], comments=[]))
    service = _service()
    user_id = uuid.uuid4()

    await service.recommend(user_id=user_id, problem=build_travel_problem())
    with pytest.raises(RateLimitExceededError):
        await service.recommend(user_id=user_id, problem=build_travel_problem())


async def test_recommend_bypasses_rate_limit_when_requested(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(algorithm_recommendation.settings, "RECOMMEND_RATE_LIMIT_PER_HOUR", 1)
    _patch_llm(monkeypatch, LlmRecommendation(ranked_names=[], comments=[]))
    service = _service()
    user_id = uuid.uuid4()

    for _ in range(3):
        await service.recommend(
            user_id=user_id, problem=build_travel_problem(), bypass_rate_limit=True
        )
