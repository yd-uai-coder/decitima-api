# DeciTima samples │ Phase 9
"""作業単位 9-7: registry / select_strategy / end-to-end + 5 strategy の比較(quality_ratio)。

knapsack_dp(9-3)/ greedy・brute_force(9-4)/ branch_and_bound(9-5)/ pulp_milp(9-6)の
単体テストはそれぞれの章にある。ここは 9-7 で新設する配線(registry / select)と、
`build_scaled_logistics_problem` を使ったプロパティテストだけ。

テスト対象 / ドライバ / スタブ:
- 対象: `select_strategy`、`REGISTRY["logistics_planning"]`、
  validate→select→solve→verify のパイプライン、5 strategy の quality_ratio 比較
- ドライバ: このテスト関数 / fixture
- スタブ: 不要 ── strategy / validation / verification はすべて純粋(`test_mst_strategies.py`
  / `test_travel_strategies.py` と同じ)
"""

from __future__ import annotations

from tests.fixtures.optimization import build_logistics_problem, build_scaled_logistics_problem

from app.algorithms.optimization.branch_and_bound_logistics import (
    BranchAndBoundLogisticsStrategy,
)
from app.algorithms.optimization.brute_force_logistics import BruteForceLogisticsStrategy
from app.algorithms.optimization.greedy_logistics import GreedyLogisticsStrategy
from app.algorithms.optimization.knapsack_dp_logistics import KnapsackDpLogisticsStrategy
from app.algorithms.optimization.pulp_logistics import PulpMilpLogisticsStrategy
from app.algorithms.registry import REGISTRY, find_strategy
from app.domain.problems.problem import NumericBoundConstraint
from app.domain.solutions.logistics import LogisticsSolution
from app.domain.solutions.solution import CandidateSolution
from app.services.algorithm_selection import select_strategy
from app.services.validation import ProblemValidationService
from app.services.verification import SolutionVerificationService

_DP = KnapsackDpLogisticsStrategy()
_GREEDY = GreedyLogisticsStrategy()
_BNB = BranchAndBoundLogisticsStrategy()
_BRUTE_FORCE = BruteForceLogisticsStrategy()
_PULP = PulpMilpLogisticsStrategy()


def _plan(sol: CandidateSolution) -> LogisticsSolution:
    assert isinstance(sol.assignments, LogisticsSolution)
    return sol.assignments


# --- registry / select ------------------------------------------------------


def test_registry_has_logistics_planning_key() -> None:
    names = [s.meta.name for s in REGISTRY["logistics_planning"]]
    assert names == ["knapsack_dp", "greedy", "branch_and_bound", "brute_force", "pulp_milp"]


def test_find_strategy_default_is_knapsack_dp() -> None:
    strategy = find_strategy(build_logistics_problem())
    assert strategy is not None and strategy.meta.name == "knapsack_dp"


def test_select_strategy_prefers_knapsack_dp() -> None:
    assert select_strategy(build_logistics_problem()).meta.name == "knapsack_dp"


def test_select_strategy_honours_requested_pulp_milp() -> None:
    assert select_strategy(build_logistics_problem(), "pulp_milp").meta.name == "pulp_milp"


# --- end-to-end(validate → select → solve → verify)-------------------------


def test_logistics_planning_end_to_end_pipeline() -> None:
    """registry に logistics_planning キーが入るこの章で初めて green(9-1〜9-6 では
    NoAlgorithmError)。"""
    problem = build_logistics_problem()
    ProblemValidationService().validate(problem)
    strategy = select_strategy(problem)
    raw = strategy.solve(problem)
    verified = SolutionVerificationService().verify(problem, raw)
    assert verified.status == "valid"
    assert verified.assignments.problem_type == "logistics_planning"
    assert verified.produced_by.name == "knapsack_dp"


def test_end_to_end_invalid_when_numeric_bound_violated() -> None:
    """total_distance に厳しい上限 → Verification が invalid(汎用チェッカーが効く)。"""
    problem = build_logistics_problem()
    capped = problem.model_copy(
        update={
            "constraints": [
                NumericBoundConstraint(
                    severity="hard", field="total_distance", operator="<=", value=1
                )
            ]
        }
    )
    raw = select_strategy(capped).solve(capped)
    verified = SolutionVerificationService().verify(capped, raw)
    assert verified.status == "invalid"


# --- 5 strategy の比較(quality_ratio)---------------------------------------


def test_all_handwritten_strategies_are_deterministic() -> None:
    p = build_logistics_problem()
    for strategy in (_DP, _GREEDY, _BNB, _BRUTE_FORCE):
        assert strategy.solve(p).model_dump() == strategy.solve(p).model_dump()


def test_handwritten_strategies_never_beat_the_brute_force_oracle() -> None:
    """brute_force が真の最適(総距離最小)。他の手実装 3 本がそれを下回ることはあり得ない
    ── quality_ratio = oracle_total / strategy_total は常に 1.0 以下になるはず。
    """
    for seed in range(6):
        problem = build_scaled_logistics_problem(6, seed=seed)
        oracle_total = _plan(_BRUTE_FORCE.solve(problem)).total_distance
        for strategy in (_DP, _GREEDY, _BNB):
            total = _plan(strategy.solve(problem)).total_distance
            assert total >= oracle_total - 1e-6, (
                f"seed={seed} strategy={strategy.meta.name} beat the oracle "
                f"({total} < {oracle_total})"
            )


def test_knapsack_dp_can_lose_to_greedy_on_travel_distance() -> None:
    """Phase 9 の教材の核: knapsack_dp は容量だけを見て詰める(移動距離を無視した上界)ので、
    地理的に離れた組合せを選び、greedy より総距離で劣ることがある(容量違反にはならない)。

    どの規模・seed で差が出るかは決定論的だが実行して初めて分かる ── ここでは
    「knapsack_dp が greedy を上回ることは無い」side を固定してプロパティ化する
    (逆に knapsack_dp が厳密に勝つことはある。DP はあくまで容量だけの上界)。
    """
    found_gap = False
    for seed in range(20):
        problem = build_scaled_logistics_problem(7, seed=seed)
        dp_total = _plan(_DP.solve(problem)).total_distance
        greedy_total = _plan(_GREEDY.solve(problem)).total_distance
        if dp_total > greedy_total + 1e-6:
            found_gap = True
        # 容量はどちらも厳密に守るので、どちらの total_distance も真の値として比較可能
    assert found_gap, "20 seed 中、knapsack_dp が greedy に距離で劣る例が一度も無かった"


def test_pulp_milp_uses_no_more_vehicles_than_any_handwritten_strategy() -> None:
    """pulp_milp は使用台数を最小化するので、他の strategy が使う台数以下になるはず。"""
    for seed in range(6):
        problem = build_scaled_logistics_problem(6, seed=seed)
        pulp_used = _PULP.solve(problem).metrics["vehicles_used"]
        for strategy in (_DP, _GREEDY, _BNB, _BRUTE_FORCE):
            used = strategy.solve(problem).metrics["vehicles_used"]
            assert pulp_used <= used + 1e-9, f"seed={seed} strategy={strategy.meta.name}"
