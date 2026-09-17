"""作業単位 11-3: `GraphState` 再設計 + `classify_problem_type`/`load_base_problem` ノード。
作業単位 11-4: `extract_objectives_constraints` ノード。
作業単位 11-5: `extract_domain_data` ノード。
作業単位 11-6: `assemble_problem`/`validate_problem` ノード。

テスト対象 / ドライバ / スタブ:
- 対象: `app.ai.graph.nodes` の各関数
- ドライバ: このテスト関数
- スタブ: LLM 呼び出しを含む関数(`classify_problem_type`/`extract_objectives_constraints`/
  `extract_domain_data`)は `FakeLLM`(外部依存の必須スタブ)。`load_base_problem`/
  `assemble_problem`/`validate_problem` は純粋(`apply_overrides`・`ProblemValidationService`
  はいずれも純粋)なのでスタブ不要。`extract_domain_data` の network_design ケースだけは
  「LLM を呼ばないこと」自体がテスト対象でスタブ不要(レイヤー設計の鏡 ── #14)

各ノードは `GraphState`(全キー必須の TypedDict)全体を受け取るが、1ノードのテストで
関係するキーだけ書きたいので、`_INITIAL_STATE` を土台に `{**_INITIAL_STATE, "text": ...}`
で上書きする(`test_structuring_workflow.py` と同じパターン)。
"""

from __future__ import annotations

import pytest
from tests.fixtures.fake_llm import FakeLLM

from app.ai.graph import nodes
from app.ai.graph.state import GraphState
from app.domain.problems.base_problems import BASE_PROBLEMS, get_base_problem
from app.domain.problems.problem import RequiredInclusionConstraint
from app.schemas.structuring import (
    ExtractedConstraint,
    ExtractedObjective,
    LogisticsDataPatch,
    ObjectivesConstraintsExtraction,
    ProblemTypeClassification,
    ProjectDataPatch,
    RouteDataPatch,
    ShiftDataPatch,
    TravelDataPatch,
)
from app.services.errors import ProblemValidationError


_INITIAL_STATE: GraphState = {
    "text": "",
    "problem_type": None,
    "base_problem": None,
    "objectives_patch": [],
    "constraints_patch": [],
    "data_patch": {},
    "notes": [],
    "problem": None,
}


def test_classify_problem_type_returns_structured_result(monkeypatch) -> None:
    monkeypatch.setattr(
        nodes,
        "get_gemini_llm",
        lambda **_: FakeLLM(structured=ProblemTypeClassification(problem_type="travel_planning")),
    )

    result = nodes.classify_problem_type(
        {**_INITIAL_STATE, "text": "5万円以内で東京を2日間旅行したい"}
    )

    assert result == {"problem_type": "travel_planning"}


def test_classify_prompt_lists_all_six_domains() -> None:
    """分類プロンプトがドメインを1つも取りこぼしていないことを確認する(私設ヘルパの回帰)。"""
    prompt = nodes._classify_prompt("dummy")
    for problem_type in BASE_PROBLEMS:
        assert problem_type in prompt


def test_load_base_problem_returns_a_fresh_copy_of_the_base_problem() -> None:
    result = nodes.load_base_problem({**_INITIAL_STATE, "problem_type": "route_planning"})

    base_problem = result["base_problem"]
    assert base_problem.problem_type == "route_planning"
    assert base_problem is not BASE_PROBLEMS["route_planning"]
    assert base_problem.data is not BASE_PROBLEMS["route_planning"].data


# (Phase 11-4)
def test_objectives_prompt_lists_catalog_ids_with_names() -> None:
    """私設ヘルパの回帰 ── カタログの id と name の両方がプロンプトに現れる。"""
    base_problem = get_base_problem("travel_planning")
    prompt = nodes._objectives_prompt("dummy", base_problem)
    assert "P1" in prompt
    assert "浅草" in prompt

def test_extract_objectives_constraints_returns_patches_from_llm(monkeypatch) -> None:
    extraction = ObjectivesConstraintsExtraction(
        objectives=[ExtractedObjective(sense="minimize", target="travel_time")],
        constraints=[ExtractedConstraint(kind="required_inclusion", items=["P1"])],
    )
    monkeypatch.setattr(nodes, "get_gemini_llm", lambda **_: FakeLLM(structured=extraction))

    result = nodes.extract_objectives_constraints(
        {
            **_INITIAL_STATE,
            "text": "浅草には必ず行きたい",
            "base_problem": get_base_problem("travel_planning"),
        }
    )

    assert result["objectives_patch"] == extraction.objectives
    assert result["constraints_patch"] == extraction.constraints

# (Phase 11-5)
@pytest.mark.parametrize(
    ("problem_type", "patch_cls"),
    [
        ("route_planning", RouteDataPatch),
        ("shift_scheduling", ShiftDataPatch),
        ("travel_planning", TravelDataPatch),
        ("project_scheduling", ProjectDataPatch),
        ("logistics_planning", LogisticsDataPatch),
    ],
)
def test_extract_domain_data_dispatches_to_the_registered_patch_schema(
    monkeypatch, problem_type, patch_cls
) -> None:
    fake = FakeLLM(structured=patch_cls())
    monkeypatch.setattr(nodes, "get_gemini_llm", lambda **_: fake)

    result = nodes.extract_domain_data(
        {
            **_INITIAL_STATE,
            "problem_type": problem_type,
            "base_problem": get_base_problem(problem_type),
        }
    )

    assert fake.structured_output_calls == [patch_cls]
    assert result == {"data_patch": {}}

def test_extract_domain_data_dumps_only_the_fields_the_llm_set(monkeypatch) -> None:
    monkeypatch.setattr(
        nodes, "get_gemini_llm", lambda **_: FakeLLM(structured=TravelDataPatch(budget=50000))
    )

    result = nodes.extract_domain_data(
        {
            **_INITIAL_STATE,
            "problem_type": "travel_planning",
            "base_problem": get_base_problem("travel_planning"),
        }
    )

    assert result == {"data_patch": {"budget": 50000}}


def test_extract_domain_data_skips_the_llm_call_for_network_design(monkeypatch) -> None:
    """network_design はトップレベル・スカラーを持たない(`EXTRACTORS` が None)ため、
    LLM を一切呼ばずに空パッチを返す。"""

    def _fail_if_called(**_kwargs: object) -> FakeLLM:
        raise AssertionError("network_design は get_gemini_llm を呼んではならない")

    monkeypatch.setattr(nodes, "get_gemini_llm", _fail_if_called)

    result = nodes.extract_domain_data(
        {
            **_INITIAL_STATE,
            "problem_type": "network_design",
            "base_problem": get_base_problem("network_design"),
        }
    )

    assert result == {"data_patch": {}}


def test_data_prompt_lists_catalog_ids_with_names() -> None:
    base_problem = get_base_problem("travel_planning")
    prompt = nodes._data_prompt("dummy", base_problem)
    assert "P1" in prompt
    assert "浅草" in prompt

# (Phase 11-6)
def test_assemble_problem_merges_all_three_patches_into_the_base() -> None:
    base = get_base_problem("travel_planning")
    state: GraphState = {
        **_INITIAL_STATE,
        "base_problem": base,
        "objectives_patch": [ExtractedObjective(sense="minimize", target="travel_time")],
        "constraints_patch": [ExtractedConstraint(kind="required_inclusion", items=["P1"])],
        "data_patch": {"budget": 50000},
    }

    result = nodes.assemble_problem(state)

    problem = result["problem"]
    assert problem.objectives[0].target == "travel_time"
    assert problem.data.budget == 50000
    assert result["notes"] == []


def test_assemble_problem_keeps_base_objectives_when_extraction_is_empty() -> None:
    base = get_base_problem("travel_planning")
    state: GraphState = {**_INITIAL_STATE, "base_problem": base}

    result = nodes.assemble_problem(state)

    assert result["problem"].objectives == base.objectives
    assert result["notes"]  # 抽出できなかった旨の注記が付く


def test_validate_problem_passes_for_an_unmodified_base_problem() -> None:
    base = get_base_problem("route_planning")
    state: GraphState = {**_INITIAL_STATE, "problem": base, "base_problem": base}
    assert nodes.validate_problem(state) == {}


def test_validate_problem_raises_for_a_hallucinated_reference() -> None:
    base = get_base_problem("travel_planning")
    bad = base.model_copy(update={"constraints": [RequiredInclusionConstraint(items=["浅草"])]})
    state: GraphState = {**_INITIAL_STATE, "problem": bad, "base_problem": base}

    with pytest.raises(ProblemValidationError):
        nodes.validate_problem(state)
