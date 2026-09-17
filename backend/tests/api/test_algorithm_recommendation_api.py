# DeciTima samples │ 初出 Phase 12
"""作業単位 12-3: `POST /api/v1/algorithms/recommend` の契約。

サービス層の振る舞い(rule/LLM のマージ・grounding・レート制限)は
`test_algorithm_recommendation_service.py` で確認済みのため、ここでは「API として
正しく配線されているか」「既存 GET /algorithms を壊していないか」だけに対象を絞る。
"""

from __future__ import annotations

from tests.fixtures.fake_llm import FakeLLM
from tests.fixtures.optimization import build_travel_problem

from app.schemas.recommendation import LlmAlgorithmComment, LlmRecommendation


def _patch_llm(monkeypatch, structured: LlmRecommendation) -> None:
    monkeypatch.setattr(
        "app.services.algorithm_recommendation.get_gemini_llm",
        lambda **_: FakeLLM(structured=structured),
    )


async def test_recommend_route_returns_candidates_with_llm_comments(api, monkeypatch) -> None:
    client, _user = api
    _patch_llm(
        monkeypatch,
        LlmRecommendation(
            ranked_names=["knapsack_dp"],
            comments=[LlmAlgorithmComment(name="knapsack_dp", comment="厳密解でおすすめ")],
        ),
    )
    problem = build_travel_problem()

    resp = await client.post(
        "/api/v1/algorithms/recommend", json={"problem": problem.model_dump(mode="json")}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["problem_type"] == "travel_planning"
    assert body["rule_preferred"] == "knapsack_dp"
    names = {r["name"] for r in body["recommendations"]}
    assert names == {"knapsack_dp", "greedy", "brute_force"}
    top = next(r for r in body["recommendations"] if r["name"] == "knapsack_dp")
    assert top["is_rule_preferred"] is True
    assert top["llm_comment"] == "厳密解でおすすめ"


async def test_list_algorithms_route_still_works_after_recommend_added(api) -> None:
    """既存 GET /algorithms(1-7)への配線を壊していないことの回帰確認。"""
    client, _user = api
    resp = await client.get("/api/v1/algorithms")
    assert resp.status_code == 200
    assert any(a["name"] == "dijkstra" for a in resp.json()["algorithms"])
