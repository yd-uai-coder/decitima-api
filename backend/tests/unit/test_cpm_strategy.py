"""作業単位 8-4: CpmScheduleStrategy / PriorityListScheduleStrategy と資源検証。

テスト対象 / ドライバ / スタブ:
- 対象: `CpmScheduleStrategy.solve`、`PriorityListScheduleStrategy.solve`、
  `verification._verify_project_resources`(SolutionVerificationService 経由)
- ドライバ: このテスト関数 / `build_project_problem` fixture(8-3)
- スタブ: 不要 ── strategy は OptimizationProblem → CandidateSolution の純粋関数、
  verification は DB を持たない

registry / select / cpm_nx / e2e は 8-6(`test_project_strategies.py`)。ここは 2 つの手実装
strategy を直接呼ぶ。
"""

from __future__ import annotations

from tests.fixtures.optimization import build_project_problem

from app.algorithms.scheduling.cpm import CpmScheduleStrategy
from app.algorithms.scheduling.priority_list import PriorityListScheduleStrategy
from app.algorithms.scheduling.project_common import peak_resource, resource_profile
from app.domain.solutions.project_manager import ProjectSolution
from app.services.verification import SolutionVerificationService

_CPM = CpmScheduleStrategy()
_PL = PriorityListScheduleStrategy()
_VERIFY = SolutionVerificationService()


def _plan(sol) -> ProjectSolution:  # noqa: ANN001
    assert isinstance(sol.assignments, ProjectSolution)
    return sol.assignments


# --- CpmScheduleStrategy -------------------------------------------------


def test_cpm_computes_the_unconstrained_schedule() -> None:
    sol = _CPM.solve(build_project_problem(resource_capacity=None))
    assert sol.status == "valid"
    assert sol.produced_by.name == "cpm"
    assert sol.metrics["makespan"] == 8.0
    assert _plan(sol).critical_path == ["A", "C", "E"]
    assert _plan(sol).problem_type == "project_scheduling"


def test_cpm_ignores_resources_and_verification_marks_it_invalid() -> None:
    """Phase 8 の教材の核: cpm は資源を無視して ES に詰める → capacity 3 では peak 4 で invalid。"""
    problem = build_project_problem(resource_capacity=3)
    verified = _VERIFY.verify(problem, _CPM.solve(problem))
    assert verified.status == "invalid"
    assert any(v.constraint_kind == "project_resource" for v in verified.violations)


def test_cpm_is_valid_when_no_resource_capacity() -> None:
    problem = build_project_problem(resource_capacity=None)
    verified = _VERIFY.verify(problem, _CPM.solve(problem))
    assert verified.status == "valid"


# --- PriorityListScheduleStrategy --------------------------------------


def test_priority_list_respects_capacity() -> None:
    problem = build_project_problem(resource_capacity=3)
    sol = _PL.solve(problem)
    assert sol.status == "valid"
    assert sol.produced_by.name == "priority_list"
    demands = {"A": 2, "B": 1, "C": 3, "D": 1, "E": 2}
    assert peak_resource(resource_profile(_plan(sol).schedule, demands)) <= 3


def test_priority_list_is_feasible_but_not_optimal() -> None:
    """貪欲は D の置き場を C に塞がれ makespan 10(下界 cpm=8 / 最適 cp_sat=9 より悪い)。"""
    problem = build_project_problem(resource_capacity=3)
    pl = _PL.solve(problem)
    cpm = _CPM.solve(build_project_problem(resource_capacity=None))
    assert _plan(pl).makespan == 10.0
    assert _plan(pl).makespan >= _plan(cpm).makespan  # feasible な解は下界以上


def test_priority_list_verification_is_valid() -> None:
    problem = build_project_problem(resource_capacity=3)
    verified = _VERIFY.verify(problem, _PL.solve(problem))
    assert verified.status == "valid"
    assert not any(v.constraint_kind == "project_resource" for v in verified.violations)


def test_priority_list_matches_cpm_without_capacity() -> None:
    problem = build_project_problem(resource_capacity=None)
    assert _plan(_PL.solve(problem)).makespan == _plan(_CPM.solve(problem)).makespan == 8.0


# --- 決定論(同じ入力 → 常に同じ出力 ------------------------------------------------------------


def test_both_strategies_are_deterministic() -> None:
    problem = build_project_problem()
    for strategy in (_CPM, _PL):
        assert strategy.solve(problem).model_dump() == strategy.solve(problem).model_dump()
