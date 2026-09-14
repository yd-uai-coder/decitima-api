# DeciTima samples │ Phase 9
"""作業単位 9-3: KnapsackDpLogisticsStrategy(容量だけを見て詰める上界)。

テスト対象 / ドライバ / スタブ:
- 対象: `KnapsackDpLogisticsStrategy.solve`
- ドライバ: このテスト関数 / `build_logistics_problem` fixture(9-1)
- スタブ: 不要 ── strategy は OptimizationProblem -> CandidateSolution の純粋関数
"""

from __future__ import annotations

from tests.fixtures.optimization import build_logistics_problem

from app.algorithms.optimization.knapsack_dp_logistics import KnapsackDpLogisticsStrategy
from app.domain.problems.logistics import LogisticsData, Vehicle
from app.domain.solutions.logistics import LogisticsSolution
from app.domain.solutions.solution import CandidateSolution

_DP = KnapsackDpLogisticsStrategy()


def _ldata(problem) -> LogisticsData:  # noqa: ANN001
    assert isinstance(problem.data, LogisticsData)
    return problem.data


def _plan(sol: CandidateSolution) -> LogisticsSolution:
    assert isinstance(sol.assignments, LogisticsSolution)
    return sol.assignments


def test_strategy_produces_valid_logistics_solution() -> None:
    sol = _DP.solve(build_logistics_problem())
    assert sol.status == "valid"
    assert sol.produced_by.name == "knapsack_dp"
    assert sol.produced_by.family == "optimization"
    assert _plan(sol).problem_type == "logistics_planning"


def test_strategy_is_deterministic() -> None:
    p = build_logistics_problem()
    assert _DP.solve(p).model_dump() == _DP.solve(p).model_dump()


def test_strategy_matches_hand_computed_optimum() -> None:
    # 容量の都合で {P1,P2} + {P3} にしか分けられない最小 fixture(Phase-9-1 §7)。
    # knapsack_dp は「単体で載らないものは除外」+「価値均一で台数最大化」なので、
    # 1台目は必ず {P1,P2}(count2、{P1,P3}/{P2,P3}は容量オーバーで到達不能)を選ぶ。
    sol = _DP.solve(build_logistics_problem())
    plan = _plan(sol)
    assert plan.total_distance == 21.0
    assert sol.metrics["vehicles_used"] == 2.0
    routes_by_stops = {frozenset(r.stop_ids) for r in plan.routes}
    assert routes_by_stops == {frozenset({"P1", "P2"}), frozenset({"P3"})}


def test_strategy_never_double_packs_beyond_capacity() -> None:
    # どの車両の合計需要も capacity を超えない(knapsack_2d が厳密に守るはず)
    problem = build_logistics_problem()
    data = _ldata(problem)
    plan = _plan(_DP.solve(problem))
    deliveries_by_id = {d.id: d for d in data.deliveries}
    vehicles_by_id = {v.id: v for v in data.vehicles}
    for route in plan.routes:
        vehicle = vehicles_by_id[route.vehicle_id]
        total_weight = sum(deliveries_by_id[sid].demand_weight for sid in route.stop_ids)
        total_volume = sum(deliveries_by_id[sid].demand_volume for sid in route.stop_ids)
        assert total_weight <= vehicle.capacity_weight
        assert total_volume <= vehicle.capacity_volume


def test_strategy_returns_infeasible_when_fleet_runs_out() -> None:
    # 車両1台だけ(容量10,10)── 合計需要16なので必ず1件は積み残る
    one_vehicle = [Vehicle(id="V1", capacity_weight=10, capacity_volume=10)]
    sol = _DP.solve(build_logistics_problem(vehicles=one_vehicle))
    assert sol.status == "infeasible"
