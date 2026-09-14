# DeciTima samples │ Phase 9
"""作業単位 9-2: logistics_common(parse / all_pairs / capacity_ok / route_for_vehicle /
route_distance / logistics_solution)+ verification._verify_logistics_routes。

テスト対象 / ドライバ / スタブ:
- 対象: `parse_logistics_problem` / `all_pairs` / `capacity_ok` / `route_for_vehicle` /
  `route_distance` / `logistics_solution` / `infeasible_logistics_solution`(いずれも純粋)、
  `SolutionVerificationService`(容量・距離の検算)
- ドライバ: このテスト関数 / `build_logistics_problem` fixture(9-1)、
  `build_logistics_solution` で手組みの解を作る
- スタブ: 不要 ── いずれも純粋(DB / Redis を触らない)
"""

from __future__ import annotations

import pytest
from tests.fixtures.optimization import (
    build_logistics_problem,
    build_logistics_solution,
    build_route_problem,
)

from app.algorithms.optimization.logistics_common import (
    all_pairs,
    capacity_ok,
    infeasible_logistics_solution,
    logistics_solution,
    parse_logistics_problem,
    route_distance,
    route_for_vehicle,
)
from app.domain.problems.logistics import DeliveryStop, LogisticsData, Vehicle
from app.domain.solutions.logistics import LogisticsSolution
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution
from app.services.verification import SolutionVerificationService

_META = AlgorithmMeta(name="test", family="optimization", implementation="handwritten")


def _ldata(problem) -> LogisticsData:  # noqa: ANN001
    assert isinstance(problem.data, LogisticsData)
    return problem.data


def _plan(sol: CandidateSolution) -> LogisticsSolution:
    assert isinstance(sol.assignments, LogisticsSolution)
    return sol.assignments


# --- parse_logistics_problem ------------------------------------------------


def test_parse_rejects_wrong_problem_type() -> None:
    with pytest.raises(TypeError):
        parse_logistics_problem(build_route_problem())


def test_parse_extracts_forbidden_segments() -> None:
    _data, forbidden = parse_logistics_problem(build_logistics_problem(forbidden=["S_D1"]))
    assert forbidden == {"S_D1"}


# --- all_pairs(Floyd-Warshall の再利用)-------------------------------------


def test_all_pairs_matches_hand_computed_distances() -> None:
    data = _ldata(build_logistics_problem())
    dist = all_pairs(data, set()) # set()はから集合のため、禁止区間(forbidden_segment_ids)なし
    # D-N1=4, D-N2=3, D-N3=6, N1-N2=2, N1-N3=(N1-N2-N3)=5, N2-N3=3
    assert dist["D"]["N1"] == 4
    assert dist["D"]["N2"] == 3
    assert dist["N1"]["N3"] == 5
    assert dist["N2"]["N3"] == 3


def test_all_pairs_excludes_forbidden_segments() -> None:
    data = _ldata(build_logistics_problem())
    dist = all_pairs(data, {"S_D1"})  # D-N1 の直接区間だけを封鎖
    # N1 へは D-N2-N1(3+2=5)で迂回するしかない(S_12 は生きている)
    assert dist["D"]["N1"] == 5


# --- capacity_ok -------------------------------------------------------------


def test_capacity_ok_checks_both_dimensions() -> None:
    vehicle = Vehicle(id="V1", capacity_weight=10, capacity_volume=10)
    fits = [DeliveryStop(id="P1", node_id="N1", demand_weight=4, demand_volume=4)]
    over_weight = [DeliveryStop(id="P1", node_id="N1", demand_weight=11, demand_volume=1)]
    assert capacity_ok(vehicle, fits)
    assert not capacity_ok(vehicle, over_weight)


# --- route_for_vehicle / route_distance -------------------------------------


def test_route_for_vehicle_visits_all_and_returns_round_trip_distance() -> None:
    data = _ldata(build_logistics_problem())
    dist = all_pairs(data, set())
    stops = [d for d in data.deliveries if d.id in ("P1", "P2")]
    result = route_for_vehicle(data.depot_id, stops, dist)
    assert result is not None
    stop_ids, distance = result
    assert set(stop_ids) == {"P1", "P2"}
    assert distance == 9.0  # D-N1-N2-D = 4+2+3(どちらの順でも 9)


def test_route_for_vehicle_empty_stops() -> None:
    data = _ldata(build_logistics_problem())
    dist = all_pairs(data, set())
    assert route_for_vehicle(data.depot_id, [], dist) == ([], 0.0)


def test_route_distance_matches_route_for_vehicle() -> None:
    data = _ldata(build_logistics_problem())
    dist = all_pairs(data, set())
    stops = [d for d in data.deliveries if d.id in ("P1", "P2")]
    result = route_for_vehicle(data.depot_id, stops, dist)
    assert result is not None
    stop_ids, distance = result

    #stop_ids に入っている各 sid に対応する node_id を探して、順番に node_order に入れる
    node_order = [next(d.node_id for d in stops if d.id == sid) for sid in stop_ids]

    # route_for_vehicleの戻り値distanceはroute_distance関数を使用しているため一致   
    assert route_distance(data.depot_id, node_order, dist) == distance


def test_route_for_vehicle_none_when_unreachable() -> None:
    data = _ldata(build_logistics_problem()).model_copy(update={"segments": []})
    dist = all_pairs(data, set())
    stops = [d for d in data.deliveries if d.id == "P1"]
    assert route_for_vehicle(data.depot_id, stops, dist) is None


# --- logistics_solution / infeasible_logistics_solution ---------------------


def test_logistics_solution_assembles_routes_and_totals() -> None:
    data = _ldata(build_logistics_problem())
    dist = all_pairs(data, set())
    sol = logistics_solution(data, {"V1": ["P1", "P2"], "V2": ["P3"]}, dist, _META, ops=42)
    assert sol.status == "valid"
    plan = _plan(sol)
    assert plan.total_distance == 21.0  # 9(P1,P2) + 12(P3)
    assert {r.vehicle_id for r in plan.routes} == {"V1", "V2"}
    assert sol.metrics["vehicles_used"] == 2.0
    assert sol.metrics["_ops"] == 42.0


def test_logistics_solution_drops_unused_vehicles() -> None:
    data = _ldata(build_logistics_problem())
    dist = all_pairs(data, set())
    sol = logistics_solution(data, {"V1": ["P1", "P2", "P3"], "V2": []}, dist, _META, ops=None)
    assert {r.vehicle_id for r in _plan(sol).routes} == {"V1"}
    assert "_ops" not in sol.metrics


def test_logistics_solution_infeasible_when_route_unreachable() -> None:
    data = _ldata(build_logistics_problem()).model_copy(update={"segments": []})
    dist = all_pairs(data, set())
    sol = logistics_solution(data, {"V1": ["P1"]}, dist, _META, ops=1)
    assert sol.status == "infeasible"


def test_infeasible_logistics_solution_shape() -> None:
    sol = infeasible_logistics_solution(_META)
    assert sol.status == "infeasible"
    assert _plan(sol).routes == []


# --- verification._verify_logistics_routes(容量・距離の検算)----------------

_HONEST = [("V1", ["P1", "P2"], 9.0), ("V2", ["P3"], 12.0)]


def test_verify_logistics_routes_passes_for_honest_solution() -> None:
    problem = build_logistics_problem()
    verified = SolutionVerificationService().verify(problem, build_logistics_solution(_HONEST))
    assert not any(v.constraint_kind == "logistics_structure" for v in verified.violations)
    assert not any(v.constraint_kind == "logistics_capacity" for v in verified.violations)


def test_verify_logistics_routes_flags_a_lying_distance() -> None:
    problem = build_logistics_problem()
    lied = [("V1", ["P1", "P2"], 999.0), ("V2", ["P3"], 12.0)]
    verified = SolutionVerificationService().verify(problem, build_logistics_solution(lied))
    assert verified.status == "invalid"
    assert any(v.constraint_kind == "logistics_structure" for v in verified.violations)


def test_verify_logistics_routes_flags_capacity_overrun() -> None:
    problem = build_logistics_problem()
    # P1+P2+P3 を 1 台に(容量 10 に対し demand 合計 16)── 距離の申告値によらず容量超過で検出される
    overloaded = [("V1", ["P1", "P2", "P3"], 0.0)]
    verified = SolutionVerificationService().verify(problem, build_logistics_solution(overloaded))
    assert verified.status == "invalid"
    assert any(v.constraint_kind == "logistics_capacity" for v in verified.violations)
