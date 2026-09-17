# DeciTima samples │ Phase 11
"""作業単位 11-1: 抽出・分類スキーマ(純粋 Pydantic)。

テスト対象 / ドライバ / スタブ:
- 対象: `app.schemas.structuring` の各 BaseModel(型定義のみ)
- ドライバ: このテスト関数
- スタブ不要 ── 対象が純粋なデータ定義で外部依存を呼ばないため
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.domain.problems.problem import (
    ForbiddenConstraint,
    NumericBoundConstraint,
    Objective,
    OptimizationProblem,
    RequiredInclusionConstraint,
    StaffingConstraint,
)
from app.domain.problems.route_planner import RouteData, RouteEdge, RouteNode
from app.schemas.structuring import (
    ExtractedConstraint,
    ExtractedObjective,
    LogisticsDataPatch,
    ObjectivesConstraintsExtraction,
    ProblemTypeClassification,
    ProjectDataPatch,
    RouteDataPatch,
    ShiftDataPatch,
    StructuringRequest,
    StructuringResponse,
    TravelDataPatch,
)

_ROUTE_DATA = RouteData(
    nodes=[RouteNode(id="A"), RouteNode(id="B")],
    edges=[RouteEdge(id="e_ab", source="A", target="B", weight=1)],
    start="A",
    goal="B",
)


def _route_problem(constraints: list) -> OptimizationProblem:
    return OptimizationProblem(
        problem_type="route_planning",
        objectives=[Objective(sense="minimize", target="total_weight")],
        constraints=constraints,
        data=_ROUTE_DATA,
    )


def test_problem_type_classification_rejects_unknown_value() -> None:
    """6種の problem_type 以外は型として弾かれる(誤答不能な Structured Output)。"""
    with pytest.raises(ValidationError):
        ProblemTypeClassification(problem_type="unknown_type")  # type: ignore[arg-type]


def test_extracted_objective_round_trips_into_objective() -> None:
    """ExtractedObjective.model_dump() がそのまま Objective の初期化引数になる。"""
    extracted = ExtractedObjective(sense="minimize", target="travel_time", weight=2.0)
    objective = Objective(**extracted.model_dump())
    assert objective.sense == "minimize"
    assert objective.target == "travel_time"
    assert objective.weight == 2.0


@pytest.mark.parametrize(
    ("kind", "extra", "expected_type"),
    [
        ("required_inclusion", {"items": ["A"]}, RequiredInclusionConstraint),
        ("forbidden", {"items": ["e_ab"]}, ForbiddenConstraint),
        ("staffing", {}, StaffingConstraint),
        (
            "numeric_bound",
            {"field": "total_weight", "operator": "<=", "value": 10.0},
            NumericBoundConstraint,
        ),
    ],
)
def test_extracted_constraint_round_trips_into_any_constraint(kind, extra, expected_type) -> None:
    """ExtractedConstraint(kind=...).model_dump(exclude_none=True) が AnyConstraint の
    discriminated union へ正しい具象型として再パースされる。"""
    extracted = ExtractedConstraint(kind=kind, **extra)
    problem = _route_problem([extracted.model_dump(exclude_none=True)])
    assert isinstance(problem.constraints[0], expected_type)


def test_extracted_constraint_omits_unset_fields_when_dumped() -> None:
    """exclude_none=True で未設定フィールド(field/operator/value/items)は dict に現れない。"""
    extracted = ExtractedConstraint(kind="staffing")
    dumped = extracted.model_dump(exclude_none=True)
    assert dumped == {"kind": "staffing", "severity": "hard"}


@pytest.mark.parametrize(
    "patch_cls",
    [RouteDataPatch, TravelDataPatch, ShiftDataPatch, ProjectDataPatch, LogisticsDataPatch],
)
def test_data_patch_defaults_to_empty_when_nothing_set(patch_cls: type) -> None:
    """全フィールド Optional ── 何も指定しなければ model_dump(exclude_unset=True) は空 dict。"""
    assert patch_cls().model_dump(exclude_unset=True) == {}


def test_route_data_patch_dumps_only_the_fields_the_llm_set() -> None:
    """一部フィールドだけ埋めた場合、exclude_unset=True でそのフィールドだけが残る。"""
    patch = RouteDataPatch(start="X")
    assert patch.model_dump(exclude_unset=True) == {"start": "X"}


def test_objectives_constraints_extraction_defaults_to_empty_lists() -> None:
    extraction = ObjectivesConstraintsExtraction()
    assert extraction.objectives == []
    assert extraction.constraints == []


def test_structuring_request_and_response_construct() -> None:
    request = StructuringRequest(text="5万円以内で東京を2日間旅行したい")
    assert request.conversation_id is None

    response = StructuringResponse(
        conversation_id=uuid.uuid4(),
        problem_type="route_planning",
        problem=_route_problem([]),
        notes=["objectives 抽出なし、シードの既定目的を使用しました"],
    )
    assert response.problem.problem_type == "route_planning"
    assert response.notes
