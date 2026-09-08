"""作業単位 6-6: 手実装の破綻 ── 全列挙オラクルで裏取り + 規模を振ったプロパティテスト。

Phase 5-2 と同型の「理論 + オラクル」章。実装ファイルは無い。

対象 = 3 手実装(Greedy / Backtracking / B&B)の最適性。
ドライバ = このテスト関数。`_brute_force_optimal` が正解オラクル(小規模専用、registry 非搭載)。
スタブ不要 ── すべて純粋。
"""

from itertools import combinations, product

from tests.fixtures.optimization import build_scaled_shift_problem, build_shift_problem

from app.algorithms.scheduling.backtracking import BacktrackingShiftStrategy
from app.algorithms.scheduling.branch_and_bound import BranchAndBoundShiftStrategy
from app.algorithms.scheduling.common import eligible_staff, respects_hard, score
from app.algorithms.scheduling.greedy import GreedyShiftStrategy
from app.domain.problems.problem import OptimizationProblem
from app.domain.problems.shift_scheduler import ShiftData
from app.domain.solutions.shift_scheduler import ShiftSolution


def _brute_force_optimal(problem: OptimizationProblem) -> float | None:
    """全割当を列挙し、hard 制約を満たすものの最良スコア。小規模専用。"""
    data = problem.data
    assert isinstance(data, ShiftData)
    slots = sorted(data.slots, key=lambda s: s.id)
    choices = [
        list(combinations([st.id for st in eligible_staff(slot, data)], slot.required_headcount))
        for slot in slots
    ]
    best: float | None = None
    for combo in product(*choices):
        assignment = {slot.id: list(picks) for slot, picks in zip(slots, combo, strict=True)}
        if not respects_hard(data, assignment):
            continue
        s, _ = score(problem, data, assignment)
        best = s if best is None else min(best, s)
    return best


def _score_of(strategy, problem: OptimizationProblem) -> float:
    data = problem.data
    assert isinstance(data, ShiftData)
    sol = strategy.solve(problem)
    assert isinstance(sol.assignments, ShiftSolution)
    s, _ = score(problem, data, sol.assignments.assignments)
    return s


def test_backtracking_and_bnb_match_the_oracle() -> None:
    problem = build_shift_problem()
    oracle = _brute_force_optimal(problem)
    assert oracle is not None
    assert _score_of(BacktrackingShiftStrategy(), problem) == oracle
    assert _score_of(BranchAndBoundShiftStrategy(), problem) == oracle


def test_greedy_is_never_better_than_the_oracle() -> None:
    problem = build_shift_problem()
    oracle = _brute_force_optimal(problem)
    assert oracle is not None
    assert _score_of(GreedyShiftStrategy(), problem) >= oracle


def test_property_small_instances_backtracking_is_optimal() -> None:
    # 規模を振っても、小さいうちは Backtracking == 全列挙の最適
    for seed in range(5):
        problem = build_scaled_shift_problem(n_staff=4, n_days=2, seed=seed)
        oracle = _brute_force_optimal(problem)
        if oracle is None:
            continue  # hard を満たす割当が無い seed はスキップ
        assert _score_of(BacktrackingShiftStrategy(), problem) == oracle


def test_medium_instance_still_terminates_for_backtracking() -> None:
    # 8 スタッフ × 3 日 × 2 スロット ── 手実装の上限付近。終わることだけ確認(数秒以内)
    problem = build_scaled_shift_problem(n_staff=8, n_days=3, seed=0)
    sol = BacktrackingShiftStrategy().solve(problem)
    assert sol.status in {"valid", "infeasible"}
