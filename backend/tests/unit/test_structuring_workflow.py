# DeciTima samples │ Phase 11
"""作業単位 11-6: `build_structuring_workflow`(複数ノードの合成、初めての end-to-end)。

テスト対象 / ドライバ / スタブ:
- 対象: `build_structuring_workflow().ainvoke(...)`
- ドライバ: このテスト関数(pytest-asyncio、`asyncio_mode = "auto"`)
- スタブ: `classify_problem_type` / `extract_objectives_constraints` / `extract_domain_data`
  の3箇所で呼ばれる `get_gemini_llm` を、呼び出し順に異なる `FakeLLM` を返す関数に
  monkeypatch する(Fake の差し込みポイントが複数ノードにまたがる ── 11-3〜11-5 の単体テストとの違い)
"""

from __future__ import annotations

import pytest
from tests.fixtures.fake_llm import FakeLLM

from app.ai.graph import nodes
from app.ai.graph.workflow import build_structuring_workflow
from app.schemas.structuring import (
    ExtractedConstraint,
    ExtractedObjective,
    ObjectivesConstraintsExtraction,
    ProblemTypeClassification,
    RouteDataPatch,
    TravelDataPatch,
)
from app.services.errors import ProblemValidationError

_INITIAL_STATE = {
    "text": "",
    "problem_type": None,
    "base_problem": None,
    "objectives_patch": [],
    "constraints_patch": [],
    "data_patch": {},
    "notes": [],
    "problem": None,
}


def _patch_llm_sequence(monkeypatch: pytest.MonkeyPatch, *fakes: FakeLLM) -> None:
    """呼び出し順に fakes を1つずつ返すよう get_gemini_llm を差し替える。"""
    iterator = iter(fakes)
    monkeypatch.setattr(nodes, "get_gemini_llm", lambda **_: next(iterator))


async def test_workflow_structures_a_travel_request_end_to_end(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """README §3.1 の例(浅草・予算5万円)を素通しできることを確認する。"""
    _patch_llm_sequence(
        monkeypatch,
        FakeLLM(structured=ProblemTypeClassification(problem_type="travel_planning")),
        FakeLLM(
            structured=ObjectivesConstraintsExtraction(
                objectives=[ExtractedObjective(sense="maximize", target="total_value")],
                constraints=[ExtractedConstraint(kind="required_inclusion", items=["P1"])],
            )
        ),
        FakeLLM(structured=TravelDataPatch(budget=50000, time_budget=16)),
    )

    workflow = build_structuring_workflow()
    result = await workflow.ainvoke(
        {**_INITIAL_STATE, "text": "5万円以内で東京を2日間旅行したい。浅草には必ず行きたい。"}
    )

    problem = result["problem"]
    assert problem.problem_type == "travel_planning"
    assert problem.data.budget == 50000
    assert problem.constraints[0].items == ["P1"]


async def test_workflow_skips_the_llm_call_for_network_design_data_extraction(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """network_design は data 抽出で LLM を呼ばない ── fakes を2つしか渡さなくても完走する。"""
    _patch_llm_sequence(
        monkeypatch,
        FakeLLM(structured=ProblemTypeClassification(problem_type="network_design")),
        FakeLLM(structured=ObjectivesConstraintsExtraction()),
    )

    workflow = build_structuring_workflow()
    result = await workflow.ainvoke({**_INITIAL_STATE, "text": "本社と支社を最小コストで結びたい"})

    assert result["problem"].problem_type == "network_design"


async def test_workflow_raises_for_a_hallucinated_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """validate_problem のグラウンディング検査がワークフロー全体を通しても効く。"""
    _patch_llm_sequence(
        monkeypatch,
        FakeLLM(structured=ProblemTypeClassification(problem_type="route_planning")),
        FakeLLM(
            structured=ObjectivesConstraintsExtraction(
                constraints=[
                    ExtractedConstraint(kind="required_inclusion", items=["存在しない場所"])
                ]
            )
        ),
        FakeLLM(structured=RouteDataPatch()),
    )

    workflow = build_structuring_workflow()
    with pytest.raises(ProblemValidationError):
        await workflow.ainvoke({**_INITIAL_STATE, "text": "存在しない場所を必ず通りたい"})
