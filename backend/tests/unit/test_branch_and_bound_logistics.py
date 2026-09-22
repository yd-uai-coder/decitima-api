"""作業単位 9-5: BranchAndBoundLogisticsStrategy(確定距離を下界に分枝限定)。

テスト対象 / ドライバ / スタブ:
- 対象: `BranchAndBoundLogisticsStrategy.solve`
- ドライバ: このテスト関数 / `build_logistics_problem` / `build_scaled_logistics_problem` fixture
- スタブ: 不要 ── strategy は純粋関数
"""

from __future__ import annotations

from tests.fixtures.optimization import build_logistics_problem, build_scaled_logistics_problem

from app.algorithms.optimization.branch_and_bound_logistics import (
    BranchAndBoundLogisticsStrategy,
)
from app.algorithms.optimization.brute_force_logistics import BruteForceLogisticsStrategy
from app.domain.solutions.logistics import LogisticsSolution
from app.domain.solutions.solution import CandidateSolution

_BNB = BranchAndBoundLogisticsStrategy()
_BRUTE_FORCE = BruteForceLogisticsStrategy()


def _plan(sol: CandidateSolution) -> LogisticsSolution:
    assert isinstance(sol.assignments, LogisticsSolution)
    return sol.assignments


def test_branch_and_bound_matches_hand_computed_optimum() -> None:
    sol = _BNB.solve(build_logistics_problem())
    assert sol.status == "valid"
    assert sol.produced_by.name == "branch_and_bound"
    assert _plan(sol).total_distance == 21.0


def test_branch_and_bound_is_deterministic() -> None:
    p = build_logistics_problem()
    assert _BNB.solve(p).model_dump() == _BNB.solve(p).model_dump()


def test_branch_and_bound_matches_brute_force_oracle_across_sizes() -> None:
    # 小規模なら分枝限定も全探索と同じ真の最適に必ず到達する(下界は安全なので取りこぼさない)
    for seed in range(4):
        problem = build_scaled_logistics_problem(5, seed=seed)
        bnb_total = _plan(_BNB.solve(problem)).total_distance
        oracle_total = _plan(_BRUTE_FORCE.solve(problem)).total_distance
        # 誤差 1e-6 未満で一致
        assert abs(bnb_total - oracle_total) < 1e-6, f"seed={seed}"


def test_branch_and_bound_never_exceeds_capacity() -> None:
    problem = build_logistics_problem()
    data = problem.data
    assert data.problem_type == "logistics_planning"
    deliveries_by_id = {d.id: d for d in data.deliveries}  # type: ignore[union-attr]
    vehicles_by_id = {v.id: v for v in data.vehicles}  # type: ignore[union-attr]
    plan = _plan(_BNB.solve(problem))
    for route in plan.routes:
        vehicle = vehicles_by_id[route.vehicle_id]
        weight = sum(deliveries_by_id[sid].demand_weight for sid in route.stop_ids)
        volume = sum(deliveries_by_id[sid].demand_volume for sid in route.stop_ids)
        assert weight <= vehicle.capacity_weight
        assert volume <= vehicle.capacity_volume
