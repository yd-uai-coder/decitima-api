"""作業単位 8-5: OrToolsCpSatProjectStrategy(CP-SAT で RCPSP を厳密に解く)。

テスト対象 / ドライバ / スタブ:
- 対象: `OrToolsCpSatProjectStrategy.solve`
- ドライバ: このテスト関数 / `build_project_problem` fixture(8-3)
- スタブ: 不要 ── OptimizationProblem → CandidateSolution の純粋関数(CP-SAT は決定論設定)
"""

from __future__ import annotations

from tests.fixtures.optimization import build_project_problem

from app.algorithms.scheduling.cpm import CpmScheduleStrategy
from app.algorithms.scheduling.ortools_project import OrToolsCpSatProjectStrategy
from app.algorithms.scheduling.priority_list import PriorityListScheduleStrategy
from app.algorithms.scheduling.project_common import peak_resource, resource_profile
from app.domain.solutions.project_manager import ProjectSolution
from app.services.verification import SolutionVerificationService

_CPSAT = OrToolsCpSatProjectStrategy()
_PL = PriorityListScheduleStrategy()
_CPM = CpmScheduleStrategy()
_DEMANDS = {"A": 2, "B": 1, "C": 3, "D": 1, "E": 2}


def _plan(sol) -> ProjectSolution:  # noqa: ANN001
    assert isinstance(sol.assignments, ProjectSolution)
    return sol.assignments


def test_cpsat_finds_the_optimal_feasible_makespan() -> None:
    problem = build_project_problem(resource_capacity=3)
    sol = _CPSAT.solve(problem)
    assert sol.status == "valid"
    assert sol.produced_by.implementation == "library:ortools"
    assert _plan(sol).makespan == 9.0  # priority_list=10 より良く、cpm の下界 8 より必ず悪くない


def test_cpsat_is_between_cpm_lower_bound_and_priority_list() -> None:
    problem = build_project_problem(resource_capacity=3)
    cpm_lb = _plan(_CPM.solve(build_project_problem(resource_capacity=None))).makespan
    cpsat = _plan(_CPSAT.solve(problem)).makespan
    pl = _plan(_PL.solve(problem)).makespan
    assert cpm_lb <= cpsat <= pl


def test_cpsat_solution_is_resource_feasible() -> None:
    problem = build_project_problem(resource_capacity=3)
    sol = _CPSAT.solve(problem)
    assert peak_resource(resource_profile(_plan(sol).schedule, _DEMANDS)) <= 3
    verified = SolutionVerificationService().verify(problem, sol)
    assert verified.status == "valid"


def test_cpsat_respects_dependencies() -> None:
    sol = _CPSAT.solve(build_project_problem(resource_capacity=3))
    by_id = {s.task_id: s for s in _plan(sol).schedule}
    assert by_id["C"].start >= by_id["A"].finish  # A -> C
    assert by_id["E"].start >= by_id["C"].finish  # C -> E


def test_cpsat_is_deterministic() -> None:
    problem = build_project_problem(resource_capacity=3)
    assert _CPSAT.solve(problem).model_dump() == _CPSAT.solve(problem).model_dump()
