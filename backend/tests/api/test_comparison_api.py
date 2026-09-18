# DeciTima samples │ 初出 Phase 14
"""作業単位 14-6: `POST /api/v1/compare` の契約。

サービス層の振る舞い(集計・エラー率・フォールバック)は `test_comparison_service.py` で
確認済みのため、ここでは「API として正しく配線されているか」だけに対象を絞る
(`test_explanation_api.py` と同じ役割分担)。
"""

from __future__ import annotations

from tests.fixtures.fake_llm import FakeLLM
from tests.fixtures.optimization import build_route_problem

from app.domain.solutions.route_planner import RouteSolution
from app.schemas.comparison import ComparisonNarrative

_SOLUTION = RouteSolution(
    path_node_ids=["A", "B", "D", "E"], path_edge_ids=["e_ab", "e_bd", "e_de"], total_weight=5
)
_NARRATIVE = ComparisonNarrative(
    summary="比較結果の要約",
    constraint_compliance_note="x",
    optimality_note="x",
    reproducibility_note="x",
    verifiability_note="x",
)


def _patch_llms(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.algorithms.llm.route_llm.get_gemini_llm",
        lambda **_: FakeLLM(structured=_SOLUTION),
    )
    monkeypatch.setattr(
        "app.services.comparison.get_gemini_llm",
        lambda **_: FakeLLM(structured=_NARRATIVE),
    )


async def test_compare_route_returns_both_paths(api, monkeypatch) -> None:
    client, _user = api
    _patch_llms(monkeypatch)
    problem = build_route_problem()

    resp = await client.post(
        "/api/v1/compare",
        json={"problem": problem.model_dump(mode="json"), "llm_runs": 2},
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["problem_type"] == "route_planning"
    assert body["algorithm_used"]["name"] == "dijkstra"
    assert len(body["llm_results"]) == 2
    assert body["metrics"]["constraint_compliance_rate_llm"] == 1.0
    assert body["narrative"]["summary"] == "比較結果の要約"


async def test_compare_rejects_llm_runs_out_of_range(api, monkeypatch) -> None:
    client, _user = api
    _patch_llms(monkeypatch)
    problem = build_route_problem()

    resp = await client.post(
        "/api/v1/compare",
        json={"problem": problem.model_dump(mode="json"), "llm_runs": 50},
    )

    assert resp.status_code == 422


async def test_solve_route_still_works_after_compare_added(api) -> None:
    """既存 POST /solve への配線を壊していないことの回帰確認。"""
    client, _user = api
    resp = await client.post(
        "/api/v1/solve", json={"problem": build_route_problem().model_dump(mode="json")}
    )
    assert resp.status_code == 200
    assert resp.json()["solution"]["status"] == "valid"
