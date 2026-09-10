# DeciTima samples │ Phase 7
"""作業単位 7-4: travel_common(build_leg_adjacency → 全点対 → 巡回順 → 検算)+ DP strategy 配線。

テスト対象 / ドライバ / スタブ:
- 対象: `build_leg_adjacency`、`travel_common.all_pairs` / `order_and_cost` / `tour_cost`、
  `KnapsackDpTravelStrategy.solve`、`verification._verify_travel_plan`
- ドライバ: このテスト関数 / `build_travel_problem` fixture(7-3)。`_tdata` / `_plan` で型を絞る
- スタブ: 不要 ── いずれも純粋(strategy は OptimizationProblem → CandidateSolution、
  verification は DB を持たない)
"""

from __future__ import annotations

from tests.fixtures.optimization import build_travel_problem

from app.algorithms.graph.adjacency import build_leg_adjacency
from app.algorithms.optimization.knapsack import KnapsackDpTravelStrategy
from app.algorithms.optimization.travel_common import all_pairs, order_and_cost, tour_cost
from app.domain.problems.problem import OptimizationProblem
from app.domain.problems.travel_planner import TravelData
from app.domain.solutions.solution import CandidateSolution
from app.domain.solutions.travel_planner import TravelSolution
from app.services.verification import SolutionVerificationService

_DP = KnapsackDpTravelStrategy()


def _tdata(problem: OptimizationProblem) -> TravelData:
    """problem.data を TravelData に絞る。"""
    assert isinstance(problem.data, TravelData)
    return problem.data


def _plan(sol: CandidateSolution) -> TravelSolution:
    """CandidateSolution.assignments を TravelSolution に絞る。"""
    assert isinstance(sol.assignments, TravelSolution)
    return sol.assignments


# --- build_leg_adjacency(TravelData → 移動 cost の隣接リスト)---------------


def test_build_leg_adjacency_is_undirected_and_uses_travel_cost() -> None:
    data = _tdata(build_travel_problem())
    adj = build_leg_adjacency(data, set())
    # L01: P0-P1 travel_cost=1 が両向きに張られる
    assert ("P1", "L01", 1.0) in adj["P0"]
    assert ("P0", "L01", 1.0) in adj["P1"]


def test_build_leg_adjacency_skips_forbidden() -> None:
    data = _tdata(build_travel_problem())
    adj = build_leg_adjacency(data, {"L01"})
    assert all(nxt != "P1" for nxt, _lid, _w in adj["P0"])


# --- all_pairs / order_and_cost / tour_cost(Floyd-Warshall 注入)-----------


def test_order_and_cost_visits_all_selected_and_returns_totals() -> None:
    data = _tdata(build_travel_problem())
    cost_dist, time_dist = all_pairs(data)
    result = order_and_cost(data, ["P1", "P3"], cost_dist, time_dist)
    assert result is not None
    visit, total_cost, total_time = result
    assert set(visit) == {"P0", "P1", "P3"}  # start=P0 が anchor で必ず入る
    assert total_cost > 0 and total_time > 0


def test_tour_cost_matches_order_and_cost() -> None:
    data = _tdata(build_travel_problem())
    cost_dist, time_dist = all_pairs(data)
    result = order_and_cost(data, ["P1", "P2"], cost_dist, time_dist)
    assert result is not None
    visit, oc, ot = result
    tc, tt = tour_cost(data, visit, cost_dist, time_dist)
    assert (tc, tt) == (oc, ot)


def test_order_and_cost_none_when_unreachable() -> None:
    # leg を全部外すと P0 以外どこにも行けない
    data = _tdata(build_travel_problem()).model_copy(update={"legs": []})
    cost_dist, time_dist = all_pairs(data)
    assert order_and_cost(data, ["P1"], cost_dist, time_dist) is None


# --- KnapsackDpTravelStrategy.solve(knapsack_2d を Travel に適用)-----------


def test_strategy_produces_valid_travel_solution() -> None:
    sol = _DP.solve(build_travel_problem())
    assert sol.status == "valid"
    assert sol.produced_by.name == "knapsack_dp"
    assert sol.produced_by.family == "optimization"
    assert _plan(sol).problem_type == "travel_planning"
    assert sol.metrics["total_value"] >= 0


def test_strategy_is_deterministic() -> None:
    p = build_travel_problem()
    assert _DP.solve(p).model_dump() == _DP.solve(p).model_dump()


def test_tight_budget_selects_fewer_places() -> None:
    loose = _DP.solve(build_travel_problem(budget=15, time_budget=15))
    tight = _DP.solve(build_travel_problem(budget=4, time_budget=4))
    assert len(_plan(tight).selected_place_ids) <= len(_plan(loose).selected_place_ids)


def test_strategy_returns_infeasible_when_selection_unreachable() -> None:
    """DP が到達不能な place を含む集合を選ぶと status="infeasible"。

    leg を全部外す + 必須 place P1 を課すと DP の選択に必ず P1 が入るが、P0→P1 が
    繋げない ── order_and_cost が None → travel_solution が infeasible。travel は
    Validation に連結性ゲートが無い(Phase-7-3 §3)ので、ここで初めて infeasible になる。
    """
    base = build_travel_problem(required=["P1"])
    problem = base.model_copy(update={"data": _tdata(base).model_copy(update={"legs": []})})
    sol = _DP.solve(problem)
    assert sol.status == "infeasible"
    assert _plan(sol).selected_place_ids == []


# --- verification._verify_travel_plan(申告コストの検算)---------------------


def test_verify_travel_plan_passes_for_honest_dp_solution() -> None:
    problem = build_travel_problem()
    verified = SolutionVerificationService().verify(problem, _DP.solve(problem))
    # DP の申告 total_cost / total_time は travel_solution が order_and_cost で計算した実値
    assert not any(v.constraint_kind == "travel_structure" for v in verified.violations)


def test_verify_travel_plan_flags_a_lying_solution() -> None:
    problem = build_travel_problem()
    honest = _DP.solve(problem)
    lied = honest.model_copy(
        update={
            "assignments": _plan(honest).model_copy(
                update={"total_cost": _plan(honest).total_cost + 999.0}
            )
        }
    )
    verified = SolutionVerificationService().verify(problem, lied)
    assert verified.status == "invalid"
    assert any(v.constraint_kind == "travel_structure" for v in verified.violations)
