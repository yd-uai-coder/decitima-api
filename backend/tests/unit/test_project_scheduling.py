# DeciTima samples │ Phase 8
"""作業単位 8-3: project_scheduling の配線(schema union / semantic / structure / 閉路ゲート)。

テスト対象 / ドライバ / スタブ:
- 対象: `ProjectData` / `ProjectSolution`(判別可能ユニオン)、`ProjectData.model_validator`、
  `SEMANTIC_CHECKS["project_scheduling"]`、`verify_project_structure`、`structural_verify` の
  project ディスパッチ arm、`ProblemValidationService.validate`(閉路 → InfeasibleProblemError)
- ドライバ: このテスト関数 / fixture
- スタブ: 不要 ── すべて純粋な値オブジェクト / 純粋関数。`ProblemValidationService` は DB を持たない

フルパイプライン(validate→select→solve→verify)は 8-6(`registry["project_scheduling"]` が
空のうちは `select_strategy` が `NoAlgorithmError` ── 進行のルール #15)。
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError
from tests.fixtures.optimization import (
    build_cyclic_project_problem,
    build_project_problem,
    build_project_solution,
)

from app.domain.problems.problem import OptimizationProblem
from app.domain.problems.project_manager import ProjectData, ProjectTask, TaskDependency
from app.domain.solutions.project_manager import ProjectSolution
from app.domain.solutions.solution import CandidateSolution
from app.domain.solutions.structure import structural_verify, verify_project_structure
from app.services.errors import InfeasibleProblemError, ProblemValidationError
from app.services.validation import ProblemValidationService

_VALIDATION = ProblemValidationService()

# CPM の正解(resource は無視した最早開始スケジュール):
#   A(0-3) C(3-7) E(7-8) がクリティカル、B(0-2) D(2-4) は slack 3、makespan 8
_CONSISTENT = [
    ("A", 0.0, 3.0, 0.0),
    ("B", 0.0, 2.0, 3.0),
    ("C", 3.0, 7.0, 0.0),
    ("D", 2.0, 4.0, 3.0),
    ("E", 7.0, 8.0, 0.0),
]


# --- 判別可能ユニオン ------------------------------------------------------


def test_problem_data_narrows_to_project_data() -> None:
    problem = build_project_problem()
    assert isinstance(problem.data, ProjectData)
    assert problem.problem_type == "project_scheduling"


def test_solution_data_narrows_to_project_solution() -> None:
    sol = build_project_solution(_CONSISTENT, critical_path=["A", "C", "E"])
    assert isinstance(sol.assignments, ProjectSolution)


def test_problem_type_must_match_data() -> None:
    with pytest.raises(ValidationError):
        OptimizationProblem(
            problem_type="route_planning",  # data は project_schedulingなのでエラーを投げる
            objectives=[],
            data=build_project_problem().data,
        )


# --- model_validator(Input Validation)-----------------------------------


def test_rejects_dependency_to_unknown_task() -> None:
    with pytest.raises(ValidationError, match="unknown task"):
        ProjectData(
            tasks=[ProjectTask(id="A", duration=1)],
            dependencies=[TaskDependency(id="d", predecessor="A", successor="ZZZ")],
        )


def test_rejects_duplicate_task_id() -> None:
    with pytest.raises(ValidationError, match="duplicate task"):
        ProjectData(tasks=[ProjectTask(id="A", duration=1), ProjectTask(id="A", duration=2)])


def test_rejects_self_dependency() -> None:
    with pytest.raises(ValidationError, match="predecessor == successor"):
        ProjectData(
            tasks=[ProjectTask(id="A", duration=1)],
            dependencies=[TaskDependency(id="d", predecessor="A", successor="A")],
        )


def test_zero_duration_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ProjectTask(id="A", duration=0)


# --- Semantic Validation -----------------------------------------------


def test_valid_project_passes_validation() -> None:
    _VALIDATION.validate(build_project_problem())  # 例外が出なければ OK


def test_empty_project_is_integrity_error() -> None:
    problem = build_project_problem()
    empty = problem.model_copy(
        update={"data": problem.data.model_copy(update={"tasks": [], "dependencies": []})}
    )
    with pytest.raises(ProblemValidationError):
        _VALIDATION.validate(empty)


def test_task_needing_more_than_capacity_is_infeasible() -> None:
    problem = build_project_problem(resource_capacity=1)  # C needs 3 > 1
    with pytest.raises(InfeasibleProblemError):
        _VALIDATION.validate(problem)


def test_dependency_cycle_is_infeasible() -> None:
    # model_validator は閉路を弾かない(走査なので) ── validation.py が has_cycle で弾く
    with pytest.raises(InfeasibleProblemError, match="cycle"):
        _VALIDATION.validate(build_cyclic_project_problem())


# --- 構造検証 -----------------------------------------------------------


def test_verify_project_structure_accepts_consistent_schedule() -> None:
    data = build_project_problem().data
    sol = build_project_solution(_CONSISTENT, critical_path=["A", "C", "E"], makespan=8.0)
    assert verify_project_structure(data, sol.assignments) == []  # type: ignore[arg-type]


def test_flags_finish_not_start_plus_duration() -> None:
    data = build_project_problem().data
    bad = [("A", 0.0, 99.0, 0.0), *_CONSISTENT[1:]]
    sol = build_project_solution(bad, critical_path=["A", "C", "E"])
    violations = verify_project_structure(data, sol.assignments)  # type: ignore[arg-type]
    assert any("finish" in v.message for v in violations)


def test_flags_dependency_violation() -> None:
    data = build_project_problem().data
    # C は A(finish 3)より前の t1 に始めてしまう
    bad = [
        ("A", 0.0, 3.0, 0.0),
        ("B", 0.0, 2.0, 3.0),
        ("C", 1.0, 5.0, 0.0),
        ("D", 2.0, 4.0, 3.0),
        ("E", 7.0, 8.0, 0.0),
    ]
    sol = build_project_solution(bad, critical_path=["A", "C", "E"], makespan=8.0)
    violations = verify_project_structure(data, sol.assignments)  # type: ignore[arg-type]
    assert any("dependency" in v.message for v in violations)


def test_flags_non_permutation_task_order() -> None:
    data = build_project_problem().data
    sol = build_project_solution(_CONSISTENT, task_order=["A", "B", "C"])  # D / E 欠け
    violations = verify_project_structure(data, sol.assignments)  # type: ignore[arg-type]
    assert any("permutation" in v.message for v in violations)


def test_flags_non_zero_slack_on_critical_path() -> None:
    data = build_project_problem().data
    # B(slack 3)を無理やりクリティカルパスに入れる
    sol = build_project_solution(_CONSISTENT, critical_path=["A", "B", "C", "E"], makespan=8.0)
    violations = verify_project_structure(data, sol.assignments)  # type: ignore[arg-type]
    assert any("slack" in v.message for v in violations)


def test_structural_verify_dispatches_project() -> None:
    # structural_verify の ProjectSolution arm が verify_project_structure に繋がっていなければ
    # ([], {}) が返り、下の any(...) が赤になる(#15 の番人。Q44)。
    problem = build_project_problem()
    bad = [("A", 0.0, 99.0, 0.0), *_CONSISTENT[1:]]
    sol: CandidateSolution = build_project_solution(bad, critical_path=["A", "C", "E"])
    violations, metrics = structural_verify(problem, sol)
    assert metrics == {}
    assert any(
        "finish" in v.message and v.constraint_kind == "project_structure" for v in violations
    )
