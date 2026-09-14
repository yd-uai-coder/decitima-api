# DeciTima samples │ Phase 9
"""作業単位 9-1: logistics_planning の配線(schema union / semantic / structure / 到達可能性ゲート)。

テスト対象 / ドライバ / スタブ:
- 対象: `LogisticsData` / `LogisticsSolution`(判別可能ユニオン)、`LogisticsData.model_validator`、
  `SEMANTIC_CHECKS["logistics_planning"]`、`verify_logistics_structure`、`structural_verify` の
  logistics ディスパッチ arm、`ProblemValidationService.validate`(到達不能 → InfeasibleProblemError)
- ドライバ: このテスト関数 / fixture
- スタブ: 不要 ── すべて純粋な値オブジェクト / 純粋関数。`ProblemValidationService` は DB を持たない

フルパイプライン(validate→select→solve→verify)は 9-7(`registry["logistics_planning"]` が
空のうちは `select_strategy` が `NoAlgorithmError` ── 進行のルール #15)。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from tests.fixtures.optimization import (
    build_disconnected_logistics_problem,
    build_logistics_problem,
    build_logistics_solution,
)

from app.domain.problems.logistics import (
    DeliveryStop,
    LogisticsData,
    LogisticsNode,
    RoadSegment,
    Vehicle,
)
from app.domain.problems.problem import OptimizationProblem
from app.domain.solutions.logistics import LogisticsSolution
from app.domain.solutions.solution import CandidateSolution
from app.domain.solutions.structure import structural_verify, verify_logistics_structure
from app.services.errors import InfeasibleProblemError
from app.services.validation import ProblemValidationService

_VALIDATION = ProblemValidationService()

# build_logistics_problem() の正解(容量の都合で {P1,P2} + {P3} にしか分けられない):
#   V1: D -> N1 -> N2 -> D(距離 9)、V2: D -> N3 -> D(距離 12)、total_distance = 21
_CONSISTENT: list[tuple[str, list[str], float]] = [
    ("V1", ["P1", "P2"], 9.0),
    ("V2", ["P3"], 12.0),
]


# --- 判別可能ユニオン ------------------------------------------------------


def test_problem_data_narrows_to_logistics_data() -> None:
    problem = build_logistics_problem()
    assert isinstance(problem.data, LogisticsData)
    assert problem.problem_type == "logistics_planning"


def test_solution_data_narrows_to_logistics_solution() -> None:
    sol = build_logistics_solution(_CONSISTENT)
    assert isinstance(sol.assignments, LogisticsSolution)


def test_problem_type_must_match_data() -> None:
    with pytest.raises(ValidationError):
        OptimizationProblem(
            problem_type="route_planning",  # data は logistics
            objectives=[],
            data=build_logistics_problem().data,
        )


# --- model_validator(Input Validation)-----------------------------------


def test_rejects_unknown_depot() -> None:
    with pytest.raises(ValidationError, match="depot_id"):
        LogisticsData(
            depot_id="ZZZ",
            nodes=[LogisticsNode(id="D")],
            segments=[],
            vehicles=[],
            deliveries=[],
        )


def test_rejects_segment_to_unknown_node() -> None:
    with pytest.raises(ValidationError, match="unknown node"):
        LogisticsData(
            depot_id="D",
            nodes=[LogisticsNode(id="D")],
            segments=[RoadSegment(id="s", source="D", target="ZZZ", distance=1)],
            vehicles=[],
            deliveries=[],
        )


def test_rejects_self_loop_segment() -> None:
    with pytest.raises(ValidationError, match="self-loop"):
        LogisticsData(
            depot_id="D",
            nodes=[LogisticsNode(id="D")],
            segments=[RoadSegment(id="s", source="D", target="D", distance=1)],
            vehicles=[],
            deliveries=[],
        )


def test_rejects_delivery_at_unknown_node() -> None:
    with pytest.raises(ValidationError, match="unknown node"):
        LogisticsData(
            depot_id="D",
            nodes=[LogisticsNode(id="D")],
            segments=[],
            vehicles=[Vehicle(id="V1", capacity_weight=10, capacity_volume=10)],
            deliveries=[DeliveryStop(id="P1", node_id="ZZZ", demand_weight=1, demand_volume=1)],
        )


def test_rejects_duplicate_node_id() -> None:
    with pytest.raises(ValidationError, match="duplicate node"):
        LogisticsData(
            depot_id="D",
            nodes=[LogisticsNode(id="D"), LogisticsNode(id="D")],
            segments=[],
            vehicles=[],
            deliveries=[],
        )


# --- Semantic Validation -----------------------------------------------


def test_valid_logistics_passes_validation() -> None:
    _VALIDATION.validate(build_logistics_problem())  # 例外が出なければ OK


def test_deliveries_without_vehicles_is_infeasible() -> None:
    problem = build_logistics_problem(vehicles=[])
    with pytest.raises(InfeasibleProblemError):
        _VALIDATION.validate(problem)


def test_delivery_exceeding_every_vehicle_capacity_is_infeasible() -> None:
    tiny = [Vehicle(id="V1", capacity_weight=1, capacity_volume=1)]
    problem = build_logistics_problem(vehicles=tiny)  # P1 の demand(4,4)が capacity(1,1)を超える
    with pytest.raises(InfeasibleProblemError):
        _VALIDATION.validate(problem)


def test_fleet_capacity_below_total_demand_is_infeasible() -> None:
    one_small_vehicle = [Vehicle(id="V1", capacity_weight=8, capacity_volume=8)]
    problem = build_logistics_problem(vehicles=one_small_vehicle)  # 合計需要 16 > 容量 8
    with pytest.raises(InfeasibleProblemError):
        _VALIDATION.validate(problem)


def test_unreachable_delivery_is_infeasible() -> None:
    # model_validator は到達可能性を見ない(走査なので) ── validation.py が判定する
    with pytest.raises(InfeasibleProblemError, match="reachable"):
        _VALIDATION.validate(build_disconnected_logistics_problem())


# --- 構造検証 -----------------------------------------------------------


def test_verify_logistics_structure_accepts_consistent_routes() -> None:
    data = build_logistics_problem().data
    sol = build_logistics_solution(_CONSISTENT)
    assert verify_logistics_structure(data, sol.assignments) == []  # type: ignore[arg-type]


def test_flags_delivery_missing_from_every_route() -> None:
    data = build_logistics_problem().data
    missing_p3 = [("V1", ["P1", "P2"], 9.0)]  # P3 がどの車両にも入っていない
    sol = build_logistics_solution(missing_p3)
    violations = verify_logistics_structure(data, sol.assignments)  # type: ignore[arg-type]
    assert any("missing" in v.message for v in violations)


def test_flags_delivery_in_two_routes() -> None:
    data = build_logistics_problem().data
    duplicated = [("V1", ["P1", "P2"], 9.0), ("V2", ["P2", "P3"], 10.0)]  # P2 が重複
    sol = build_logistics_solution(duplicated)
    violations = verify_logistics_structure(data, sol.assignments)  # type: ignore[arg-type]
    assert any("more than one route" in v.message for v in violations)


def test_flags_total_distance_mismatch() -> None:
    data = build_logistics_problem().data
    sol = build_logistics_solution(_CONSISTENT, total_distance=999.0)
    violations = verify_logistics_structure(data, sol.assignments)  # type: ignore[arg-type]
    assert any("total_distance" in v.message for v in violations)


def test_flags_unknown_vehicle() -> None:
    data = build_logistics_problem().data
    sol = build_logistics_solution([("ZZZ", ["P1", "P2"], 9.0), ("V2", ["P3"], 12.0)])
    violations = verify_logistics_structure(data, sol.assignments)  # type: ignore[arg-type]
    assert any("unknown vehicle" in v.message for v in violations)


def test_structural_verify_dispatches_logistics() -> None:
    # structural_verify の LogisticsSolution arm が verify_logistics_structure に繋がっていなければ
    # ([], {}) が返り、下の any(...) が赤になる(#15 の番人。project の Q44 と同型)。
    problem = build_logistics_problem()
    sol: CandidateSolution = build_logistics_solution(_CONSISTENT, total_distance=999.0)
    violations, metrics = structural_verify(problem, sol)
    assert metrics == {}
    assert any(
        "total_distance" in v.message and v.constraint_kind == "logistics_structure"
        for v in violations
    )
