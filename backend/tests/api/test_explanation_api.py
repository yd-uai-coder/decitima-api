# DeciTima samples │ 初出 Phase 13
"""作業単位 13-3: `POST /api/v1/solutions/{solution_id}/explain` の契約。

サービス層の振る舞い(LLM呼び出し・フォールバック・レート制限)は
`test_explanation_service.py` で確認済みのため、ここでは「API として正しく配線されているか」
「既存 GET /solutions/{id} を壊していないか」「404 が伝播するか」だけに対象を絞る
(`test_algorithm_recommendation_api.py` と同じ役割分担)。
"""

from __future__ import annotations

import uuid

from tests.fixtures.fake_llm import FakeLLM
from tests.fixtures.optimization import build_route_problem

from app.schemas.explanation import LlmExplanation


def _patch_llm(monkeypatch, structured: LlmExplanation) -> None:
    monkeypatch.setattr(
        "app.services.explanation.get_gemini_llm",
        lambda **_: FakeLLM(structured=structured),
    )


async def test_explain_route_returns_narrative_for_persisted_solution(api, monkeypatch) -> None:
    client, _user = api
    _patch_llm(
        monkeypatch,
        LlmExplanation(
            why_this_solution="必須経由地 C を満たしつつ最短の経路です",
            key_constraints="C を必ず経由する制約が効いています",
            algorithm_rationale="非負辺なので dijkstra を使いました",
            alternatives_comparison="bellman_ford は負辺対応ですが今回は不要です",
            improvement_notes="改善余地はありません",
        ),
    )
    problem = build_route_problem(forbidden=["e_bd"], required=["C"])
    solve = await client.post("/api/v1/solve", json={"problem": problem.model_dump(mode="json")})
    solution_id = solve.json()["solution_id"]

    resp = await client.post(f"/api/v1/solutions/{solution_id}/explain")

    assert resp.status_code == 200
    body = resp.json()
    assert body["solution_id"] == solution_id
    assert body["algorithm_name"] == "dijkstra"
    assert "C" in body["key_constraints"]
    assert body["notes"] == []


async def test_explain_route_404_for_unknown_solution(api) -> None:
    client, _user = api
    resp = await client.post(f"/api/v1/solutions/{uuid.uuid4()}/explain")
    assert resp.status_code == 404


async def test_get_solution_route_still_works_after_explain_added(api) -> None:
    """既存 GET /solutions/{id}(1-7)への配線を壊していないことの回帰確認。"""
    client, _user = api
    solve = await client.post(
        "/api/v1/solve",
        json={"problem": build_route_problem().model_dump(mode="json")},
    )
    solution_id = solve.json()["solution_id"]

    resp = await client.get(f"/api/v1/solutions/{solution_id}")
    assert resp.status_code == 200
    assert resp.json()["status"] == "valid"
