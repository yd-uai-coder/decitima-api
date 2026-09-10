# DeciTima samples │ Phase 7
"""作業単位 7-5: Greedy / BruteForce オラクル / registry / select / end-to-end。

訪問順(`build_leg_adjacency` / `all_pairs` / `order_and_cost` / `tour_cost`)と DP strategy の
テストは 7-4 の `test_travel_common.py`。ここは 7-5 で新設する 2 strategy と配線・e2e だけ。

テスト対象 / ドライバ / スタブ:
- 対象: `GreedyTravelStrategy`、`BruteForceTravelStrategy`、`select_strategy`、
  validate→select→solve→verify のパイプライン
- ドライバ: このテスト関数 / fixture
- スタブ: 不要 ── strategy / validation / verification はすべて純粋(DB を持たない。Redis は
  `SolveService` の関心事で、ここでは各段を直接呼ぶ ── `test_mst_strategies.py` と同じ)
"""

from __future__ import annotations

from tests.fixtures.optimization import build_scaled_travel_problem, build_travel_problem

from app.algorithms.graph.floyd_warshall import AllPairs
from app.algorithms.optimization.brute_force_travel import BruteForceTravelStrategy
from app.algorithms.optimization.greedy_travel import GreedyTravelStrategy
from app.algorithms.optimization.knapsack import KnapsackDpTravelStrategy
from app.algorithms.optimization.travel_common import all_pairs, tour_cost
from app.algorithms.registry import REGISTRY, find_strategy
from app.domain.problems.problem import OptimizationProblem
from app.domain.problems.travel_planner import TravelData
from app.domain.solutions.solution import CandidateSolution
from app.domain.solutions.travel_planner import TravelSolution
from app.services.algorithm_selection import select_strategy
from app.services.validation import ProblemValidationService
from app.services.verification import SolutionVerificationService

_DP = KnapsackDpTravelStrategy()
_GREEDY = GreedyTravelStrategy()
_BRUTE = BruteForceTravelStrategy()


def _tdata(problem: OptimizationProblem) -> TravelData:
    """problem.data を TravelData に絞る。"""
    assert isinstance(problem.data, TravelData)
    return problem.data


def _plan(sol: CandidateSolution) -> TravelSolution:
    """CandidateSolution.assignments を TravelSolution に絞る。"""
    assert isinstance(sol.assignments, TravelSolution)
    return sol.assignments


def _real_value(
    sol: CandidateSolution, data: TravelData, cost_dist: AllPairs, time_dist: AllPairs
) -> float:
    """移動込みの真の効用。予算 or 時間を超えていたら -inf(実行不可能)。"""
    tc, tt = tour_cost(data, _plan(sol).visit_order, cost_dist, time_dist)
    if tc > data.budget + 1e-6 or tt > data.time_budget + 1e-6:
        return float("-inf")
    return _plan(sol).total_value


# --- Greedy / BruteForce(7-5)-----------------------------------------


def test_greedy_produces_feasible_plan() -> None:
    problem = build_travel_problem(budget=20, time_budget=20)
    data = _tdata(problem)
    sol = _GREEDY.solve(problem)
    assert sol.status == "valid"
    assert sol.produced_by.name == "greedy"
    # Greedy は 1 手ごとに実際の巡回コストで判定するので、必ず予算・時間内
    assert _plan(sol).total_cost <= data.budget + 1e-6
    assert _plan(sol).total_time <= data.time_budget + 1e-6


def test_dp_can_overrun_because_it_ignores_travel_cost() -> None:
    """Phase 7 の教材の核: DP は place だけで詰める → 移動分を足すと予算を超えることがある。

    budget=20 で place 費用(18)は DP に収まるが、閉路の移動費用(5)を足すと 23 > 20。
    Verification が hard で `invalid` にする。同じ問題で Greedy は移動込みで詰めるので valid。
    """
    problem = build_travel_problem(budget=20, time_budget=20)
    dp = _DP.solve(problem)
    dp_verified = SolutionVerificationService().verify(problem, dp)
    greedy_verified = SolutionVerificationService().verify(problem, _GREEDY.solve(problem))
    assert dp_verified.status == "invalid"
    assert greedy_verified.status == "valid"


def test_brute_force_is_the_oracle_dp_and_greedy_never_beat_it() -> None:
    """小規模では BruteForce が真の最適。DP / Greedy はそれ以下(移動込みの真値で比較)。"""
    for seed in range(6):
        problem = build_scaled_travel_problem(n_places=6, seed=seed)
        data = _tdata(problem)
        cost_dist, time_dist = all_pairs(data)

        best = _real_value(_BRUTE.solve(problem), data, cost_dist, time_dist)
        assert _real_value(_DP.solve(problem), data, cost_dist, time_dist) <= best + 1e-6
        assert _real_value(_GREEDY.solve(problem), data, cost_dist, time_dist) <= best + 1e-6


def test_all_strategies_are_deterministic() -> None:
    p = build_travel_problem()
    for strategy in (_DP, _GREEDY, _BRUTE):
        assert strategy.solve(p).model_dump() == strategy.solve(p).model_dump()


# --- registry / select(7-5)-----------------------------------------


def test_registry_has_travel_planning_key() -> None:
    names = [s.meta.name for s in REGISTRY["travel_planning"]]
    assert names == ["knapsack_dp", "greedy", "brute_force"]


def test_find_strategy_default_is_knapsack_dp() -> None:
    strategy = find_strategy(build_travel_problem())
    assert strategy is not None and strategy.meta.name == "knapsack_dp"


def test_select_strategy_prefers_knapsack_dp() -> None:
    assert select_strategy(build_travel_problem()).meta.name == "knapsack_dp"


def test_select_strategy_honours_requested_brute_force() -> None:
    assert select_strategy(build_travel_problem(), "brute_force").meta.name == "brute_force"


# --- end-to-end(validate → select → solve → verify)-----------------


def test_travel_planning_end_to_end_pipeline() -> None:
    """registry に travel_planning キーが入るこの章で初めて green(7-3 では NoAlgorithmError)。"""
    problem = build_travel_problem()
    ProblemValidationService().validate(problem)
    strategy = select_strategy(problem)
    raw = strategy.solve(problem)
    verified = SolutionVerificationService().verify(problem, raw)
    assert verified.status == "valid"  # DP は place だけで詰める → 予算・時間内、嘘もない
    assert verified.assignments.problem_type == "travel_planning"
    assert verified.produced_by.name == "knapsack_dp"


def test_end_to_end_invalid_when_numeric_bound_violated() -> None:
    """total_cost に厳しい上限 → Verification が invalid(汎用チェッカーが travel 解に効く)。"""
    from app.domain.problems.problem import NumericBoundConstraint

    problem = build_travel_problem()
    capped = problem.model_copy(
        update={
            "constraints": [
                NumericBoundConstraint(severity="hard", field="total_cost", operator="<=", value=1)
            ]
        }
    )
    raw = select_strategy(capped).solve(capped)
    verified = SolutionVerificationService().verify(capped, raw)
    assert verified.status == "invalid"
