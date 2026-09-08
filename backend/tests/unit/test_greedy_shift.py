"""作業単位 6-3: GreedyShiftStrategy。

対象 = `GreedyShiftStrategy.solve`(純粋)+ `scheduling/common.py`。ドライバ = このテスト関数。
スタブ不要 ── solve は純粋、DB / Redis を触らない。
"""

from tests.fixtures.optimization import (
    build_infeasible_shift_problem,
    build_shift_problem,
)

from app.algorithms.scheduling.common import eligible_staff, respects_hard
from app.algorithms.scheduling.greedy import GreedyShiftStrategy
from app.domain.problems.shift_scheduler import ShiftData
from app.domain.solutions.shift_scheduler import ShiftSolution
from app.services.verification import SolutionVerificationService

_STRATEGY = GreedyShiftStrategy()


def _shift(sol) -> ShiftSolution:
    assert isinstance(sol.assignments, ShiftSolution)
    return sol.assignments


def test_solve_fills_every_slot_on_the_example() -> None:
    sol = _STRATEGY.solve(build_shift_problem())
    assert sol.status == "valid"
    picks = _shift(sol).assignments
    assert set(picks) == {"s1", "s2", "s3", "s4"}
    assert all(len(v) == 1 for v in picks.values())
    assert "_ops" in sol.metrics  # 手実装トラック → 操作回数あり


def test_verified_solution_respects_hard_constraints() -> None:
    problem = build_shift_problem()
    verified = SolutionVerificationService().verify(problem, _STRATEGY.solve(problem))
    assert verified.status == "valid"
    assert verified.metrics["day_off_satisfaction"] == 1.0
    data = problem.data
    assert isinstance(data, ShiftData)
    assert respects_hard(data, _shift(verified).assignments)


def test_greedy_may_return_invalid_when_it_cannot_fill() -> None:
    # s1 は 2 人必要だが入れるスタッフは 1 人 ── Greedy は例外でなく invalid な候補を返す
    problem = build_infeasible_shift_problem()
    raw = _STRATEGY.solve(problem)
    assert raw.status == "valid"  # strategy は「作れた分」を valid で返す
    verified = SolutionVerificationService().verify(problem, raw)
    assert verified.status == "invalid"  # Verification が hard 違反を検出


def test_deterministic_same_input_same_output() -> None:
    p = build_shift_problem()
    assert _STRATEGY.solve(p).model_dump() == _STRATEGY.solve(p).model_dump()


def test_eligible_staff_is_wage_sorted_and_skill_filtered() -> None:
    data = build_shift_problem().data
    assert isinstance(data, ShiftData)
    s1 = next(s for s in data.slots if s.id == "s1")
    names = [st.id for st in eligible_staff(s1, data)]
    assert names == ["sato", "ito", "tanaka"]  # 時給 1000 / 1100 / 1200
