"""作業単位 6-5: BranchAndBoundShiftStrategy。

対象 = `BranchAndBoundShiftStrategy.solve`(純粋)。ドライバ = このテスト関数。スタブ不要。
"""

from tests.fixtures.optimization import build_shift_problem

from app.algorithms.scheduling.backtracking import BacktrackingShiftStrategy
from app.algorithms.scheduling.branch_and_bound import BranchAndBoundShiftStrategy
from app.algorithms.scheduling.common import score
from app.domain.problems.shift_scheduler import ShiftData
from app.domain.solutions.shift_scheduler import ShiftSolution
from app.services.verification import SolutionVerificationService

_STRATEGY = BranchAndBoundShiftStrategy()


def _assignments(sol) -> dict[str, list[str]]:
    assert isinstance(sol.assignments, ShiftSolution)
    return sol.assignments.assignments


def test_finds_same_optimum_as_backtracking() -> None:
    problem = build_shift_problem()
    data = problem.data
    assert isinstance(data, ShiftData)
    bnb = _STRATEGY.solve(problem)
    bt = BacktrackingShiftStrategy().solve(problem)
    assert bnb.status == "valid"
    s_bnb, _ = score(problem, data, _assignments(bnb))
    s_bt, _ = score(problem, data, _assignments(bt))
    assert s_bnb == s_bt  # 下界で枝を切っても最適解は変わらない


def test_bound_prunes_fewer_nodes_than_plain_backtracking() -> None:
    problem = build_shift_problem()
    bnb_ops = _STRATEGY.solve(problem).metrics["_ops"]
    bt_ops = BacktrackingShiftStrategy().solve(problem).metrics["_ops"]
    assert bnb_ops < bt_ops  # 下界による枝刈りの効果


def test_verified_valid_on_the_example() -> None:
    problem = build_shift_problem()
    verified = SolutionVerificationService().verify(problem, _STRATEGY.solve(problem))
    assert verified.status == "valid"
    assert verified.metrics["labor_cost"] == 20000.0


def test_not_truncated_on_small_problem() -> None:
    # 小規模ではノード予算を使い切らない → _truncated は付かない
    sol = _STRATEGY.solve(build_shift_problem())
    assert "_truncated" not in sol.metrics


def test_deterministic_same_input_same_output() -> None:
    p = build_shift_problem()
    assert _STRATEGY.solve(p).model_dump() == _STRATEGY.solve(p).model_dump()
