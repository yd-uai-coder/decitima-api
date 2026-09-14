# DeciTima samples │ Phase 9
"""作業単位 9-4: GreedyLogisticsStrategy(常に valid)+ BruteForceLogisticsStrategy(正解オラクル)。

テスト対象 / ドライバ / スタブ:
- 対象: `GreedyLogisticsStrategy.solve` / `BruteForceLogisticsStrategy.solve`
- ドライバ: このテスト関数 / `build_logistics_problem` fixture(9-1)
- スタブ: 不要 ── いずれも純粋関数
"""

from __future__ import annotations

from tests.fixtures.optimization import build_logistics_problem

from app.algorithms.optimization.brute_force_logistics import BruteForceLogisticsStrategy
from app.algorithms.optimization.greedy_logistics import GreedyLogisticsStrategy
from app.domain.problems.logistics import Vehicle
from app.domain.solutions.logistics import LogisticsSolution
from app.domain.solutions.solution import CandidateSolution

_GREEDY = GreedyLogisticsStrategy()
_BRUTE_FORCE = BruteForceLogisticsStrategy()


def _plan(sol: CandidateSolution) -> LogisticsSolution:
    assert isinstance(sol.assignments, LogisticsSolution)
    return sol.assignments


# --- GreedyLogisticsStrategy -------------------------------------------------


def test_greedy_produces_valid_logistics_solution() -> None:
    sol = _GREEDY.solve(build_logistics_problem())
    assert sol.status == "valid"
    assert sol.produced_by.name == "greedy"


def test_greedy_matches_hand_computed_optimum() -> None:
    # 最小 fixture では {P1,P2} + {P3} しか作れないので greedy も 21 に一致する
    sol = _GREEDY.solve(build_logistics_problem())
    assert _plan(sol).total_distance == 21.0


def test_greedy_never_exceeds_capacity() -> None:
    problem = build_logistics_problem()
    data = problem.data
    assert data.problem_type == "logistics_planning"
    deliveries_by_id = {d.id: d for d in data.deliveries}  # type: ignore[union-attr]
    vehicles_by_id = {v.id: v for v in data.vehicles}  # type: ignore[union-attr]
    plan = _plan(_GREEDY.solve(problem))
    for route in plan.routes:
        vehicle = vehicles_by_id[route.vehicle_id]
        weight = sum(deliveries_by_id[sid].demand_weight for sid in route.stop_ids)
        volume = sum(deliveries_by_id[sid].demand_volume for sid in route.stop_ids)
        assert weight <= vehicle.capacity_weight
        assert volume <= vehicle.capacity_volume


def test_greedy_returns_infeasible_when_fleet_runs_out() -> None:
    one_vehicle = [Vehicle(id="V1", capacity_weight=10, capacity_volume=10)]
    sol = _GREEDY.solve(build_logistics_problem(vehicles=one_vehicle))
    assert sol.status == "infeasible"


# --- BruteForceLogisticsStrategy --------------------------------------------


def test_brute_force_finds_the_true_optimum() -> None:
    sol = _BRUTE_FORCE.solve(build_logistics_problem())
    assert sol.status == "valid"
    assert _plan(sol).total_distance == 21.0  # 例題では唯一の実行可能な分け方と一致


def test_brute_force_is_deterministic() -> None:
    p = build_logistics_problem()
    assert _BRUTE_FORCE.solve(p).model_dump() == _BRUTE_FORCE.solve(p).model_dump()


def test_brute_force_never_beats_by_exceeding_capacity() -> None:
    problem = build_logistics_problem()
    data = problem.data
    assert data.problem_type == "logistics_planning"
    deliveries_by_id = {d.id: d for d in data.deliveries}  # type: ignore[union-attr]
    vehicles_by_id = {v.id: v for v in data.vehicles}  # type: ignore[union-attr]
    plan = _plan(_BRUTE_FORCE.solve(problem))
    for route in plan.routes:
        vehicle = vehicles_by_id[route.vehicle_id]
        weight = sum(deliveries_by_id[sid].demand_weight for sid in route.stop_ids)
        volume = sum(deliveries_by_id[sid].demand_volume for sid in route.stop_ids)
        assert weight <= vehicle.capacity_weight
        assert volume <= vehicle.capacity_volume


def test_greedy_is_never_better_than_brute_force_oracle() -> None:
    # brute_force は真の最適 ── greedy がそれを下回る(より小さい)ことはあり得ない
    problem = build_logistics_problem()
    greedy_total = _plan(_GREEDY.solve(problem)).total_distance
    optimal_total = _plan(_BRUTE_FORCE.solve(problem)).total_distance
    assert greedy_total >= optimal_total - 1e-9
