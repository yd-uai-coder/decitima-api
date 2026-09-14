# DeciTima samples │ Phase 9
"""作業単位 9-6: PulpMilpLogisticsStrategy(使用台数最小化のビンパッキング MILP)。

テスト対象 / ドライバ / スタブ:
- 対象: `PulpMilpLogisticsStrategy.solve`
- ドライバ: このテスト関数 / `build_logistics_problem` fixture(9-1)
- スタブ: 不要 ── strategy は純粋関数(CBC はプロセス内で完結する組み込みソルバー)
"""

from __future__ import annotations

from tests.fixtures.optimization import build_logistics_problem

from app.algorithms.optimization.pulp_logistics import PulpMilpLogisticsStrategy
from app.domain.problems.logistics import Vehicle
from app.domain.solutions.logistics import LogisticsSolution
from app.domain.solutions.solution import CandidateSolution
from app.services.verification import SolutionVerificationService

_PULP = PulpMilpLogisticsStrategy()


def _plan(sol: CandidateSolution) -> LogisticsSolution:
    assert isinstance(sol.assignments, LogisticsSolution)
    return sol.assignments


def test_pulp_produces_valid_logistics_solution() -> None:
    sol = _PULP.solve(build_logistics_problem())
    assert sol.status == "valid"
    assert sol.produced_by.name == "pulp_milp"
    assert sol.produced_by.implementation == "library:pulp"
    assert "_ops" not in sol.metrics  # ライブラリトラックは _ops を出さない


def test_pulp_minimizes_vehicle_count() -> None:
    # 例題は容量の都合で最低2台必要 ── 3台目の余裕があっても使用台数は2のまま
    three_vehicles = [
        Vehicle(id="V1", capacity_weight=10, capacity_volume=10),
        Vehicle(id="V2", capacity_weight=10, capacity_volume=10),
        Vehicle(id="V3", capacity_weight=10, capacity_volume=10),
    ]
    sol = _PULP.solve(build_logistics_problem(vehicles=three_vehicles))
    assert sol.metrics["vehicles_used"] == 2.0


def test_pulp_assigns_every_delivery_exactly_once() -> None:
    plan = _plan(_PULP.solve(build_logistics_problem()))
    all_ids = sorted(sid for r in plan.routes for sid in r.stop_ids)
    assert all_ids == ["P1", "P2", "P3"]


def test_pulp_solution_passes_verification() -> None:
    # 割当後の巡回順は TSP 近似(logistics_common)に委譲しているので、容量・距離とも整合するはず
    problem = build_logistics_problem()
    verified = SolutionVerificationService().verify(problem, _PULP.solve(problem))
    assert verified.status == "valid"
    assert verified.violations == []


def test_pulp_returns_infeasible_when_fleet_too_small() -> None:
    tiny = [Vehicle(id="V1", capacity_weight=1, capacity_volume=1)]
    sol = _PULP.solve(build_logistics_problem(vehicles=tiny))
    assert sol.status == "infeasible"
