"""作業単位 6-4: BacktrackingShiftStrategy。

対象 = `BacktrackingShiftStrategy.solve`(純粋)。ドライバ = このテスト関数。スタブ不要。
"""

from tests.fixtures.optimization import build_shift_problem

from app.algorithms.scheduling.backtracking import BacktrackingShiftStrategy
from app.algorithms.scheduling.common import score
from app.domain.problems.shift_scheduler import ShiftData
from app.domain.solutions.shift_scheduler import ShiftSolution
from app.services.verification import SolutionVerificationService

_STRATEGY = BacktrackingShiftStrategy()


def _shift(sol) -> ShiftSolution:
    assert isinstance(sol.assignments, ShiftSolution)
    return sol.assignments


def test_solve_finds_optimal_on_the_example() -> None:
    problem = build_shift_problem()
    sol = _STRATEGY.solve(problem)
    assert sol.status == "valid"
    verified = SolutionVerificationService().verify(problem, sol)
    assert verified.status == "valid"
    # 最安の sato が全スロットを担当 = labor_cost 最小、希望休は全員満たす
    assert verified.metrics["labor_cost"] == 20000.0
    assert verified.metrics["day_off_satisfaction"] == 1.0


def test_no_better_assignment_exists() -> None:
    # Backtracking の解より良いスコアの割当は無い(全探索の帰結)
    problem = build_shift_problem()
    data = problem.data
    assert isinstance(data, ShiftData)
    best_score, _ = score(problem, data, _shift(_STRATEGY.solve(problem)).assignments)
    # 手組みの別解(sato を分散)より良い or 同等
    alt = {"s1": ["sato"], "s2": ["sato"], "s3": ["ito"], "s4": ["tanaka"]}
    alt_score, _ = score(problem, data, alt)
    assert best_score <= alt_score


def test_deterministic_same_input_same_output() -> None:
    p = build_shift_problem()
    assert _STRATEGY.solve(p).model_dump() == _STRATEGY.solve(p).model_dump()


def test_reports_ops_count() -> None:
    sol = _STRATEGY.solve(build_shift_problem())
    assert sol.metrics["_ops"] > 0  # 展開したノード数
