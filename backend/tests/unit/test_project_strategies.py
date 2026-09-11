# DeciTima samples │ Phase 8
"""作業単位 8-6: registry / select / cpm_nx オラクル / end-to-end。

cpm / priority_list の solve テストは 8-4(`test_cpm_strategy.py`)、cp_sat は 8-5。
ここは registry 配線・select・別実装オラクルの検算・フルパイプラインだけ。

テスト対象 / ドライバ / スタブ:
- 対象: `REGISTRY["project_scheduling"]`、`select_strategy`、`NetworkxCpmStrategy`、
  validate→select→solve→verify のパイプライン
- ドライバ: このテスト関数 / fixture
- スタブ: 不要 ── strategy / validation / verification はすべて純粋(`test_mst_strategies.py` と同型)
"""

from __future__ import annotations

from tests.fixtures.optimization import build_project_problem, build_scaled_project_problem

from app.algorithms.registry import REGISTRY, find_strategy
from app.algorithms.scheduling.cpm import CpmScheduleStrategy
from app.algorithms.scheduling.networkx_project import NetworkxCpmStrategy
from app.domain.problems.problem import NumericBoundConstraint
from app.domain.solutions.project_manager import ProjectSolution
from app.services.algorithm_selection import select_strategy
from app.services.validation import ProblemValidationService
from app.services.verification import SolutionVerificationService

_CPM = CpmScheduleStrategy()
_NX = NetworkxCpmStrategy()
_VALIDATE = ProblemValidationService()
_VERIFY = SolutionVerificationService()


def _plan(sol) -> ProjectSolution:  # noqa: ANN001
    assert isinstance(sol.assignments, ProjectSolution)
    return sol.assignments


# --- registry / select ------------------------------------------------


def test_registry_has_project_scheduling_key() -> None:
    names = [s.meta.name for s in REGISTRY["project_scheduling"]]
    assert names == ["cpm", "priority_list", "cp_sat", "cpm_nx"]
    # 手実装が先頭(?algorithm=cpm は library:networkx でなく手実装が当たる)
    assert REGISTRY["project_scheduling"][0].meta.implementation == "handwritten"


def test_find_strategy_default_is_first_candidate() -> None:
    strategy = find_strategy(build_project_problem())
    assert strategy is not None and strategy.meta.name == "cpm"


def test_select_prefers_priority_list_when_resource_constrained() -> None:
    assert select_strategy(build_project_problem(resource_capacity=3)).meta.name == "priority_list"


def test_select_prefers_cpm_when_no_capacity() -> None:
    assert select_strategy(build_project_problem(resource_capacity=None)).meta.name == "cpm"


def test_select_honours_requested_cp_sat() -> None:
    s = select_strategy(build_project_problem(), "cp_sat")
    assert s.meta.name == "cp_sat" and s.meta.implementation == "library:ortools"


# --- 別実装オラクル(手実装 cpm ⟷ networkx)---------------------------


def test_cpm_and_cpm_nx_agree_on_makespan_and_critical_tasks() -> None:
    for seed in range(6):
        problem = build_scaled_project_problem(n_tasks=10, seed=seed)
        hand = _plan(_CPM.solve(problem))
        nx_sol = _plan(_NX.solve(problem))
        assert hand.makespan == nx_sol.makespan
        # 「どのタスクが余裕ゼロ(クリティカル)か」は両実装で一致(複数のクリティカルパスが
        # あるとき chain はタイブレークで 1 本に絞るので、集合で比べる)
        hand_critical = {s.task_id for s in hand.schedule if s.slack == 0}
        nx_critical = {s.task_id for s in nx_sol.schedule if s.slack == 0}
        assert hand_critical == nx_critical
        assert hand.critical_path == nx_sol.critical_path  # tie-break も一致


def test_cpm_nx_is_a_library_strategy_without_ops() -> None:
    sol = _NX.solve(build_project_problem(resource_capacity=None))
    assert sol.produced_by.implementation == "library:networkx"
    assert "_ops" not in sol.metrics


# --- end-to-end(validate → select → solve → verify)-----------------


def test_project_end_to_end_pipeline_no_capacity() -> None:
    """registry に project_scheduling キーが入るこの章で初めて green(8-3 では NoAlgorithmError)。"""
    problem = build_project_problem(resource_capacity=None)
    _VALIDATE.validate(problem)
    raw = select_strategy(problem).solve(problem)
    verified = _VERIFY.verify(problem, raw)
    assert verified.status == "valid"
    assert verified.assignments.problem_type == "project_scheduling"
    assert verified.produced_by.name == "cpm"


def test_three_way_cpm_infeasible_priority_list_feasible_cpsat_optimal() -> None:
    """Phase 8 の教材の核 ── 資源 capacity 3 で:
    cpm(資源無視 = 下界)→ verify で invalid / priority_list(feasible)→ valid /
    cp_sat(厳密最適)→ valid かつ priority_list 以下の makespan。
    """
    problem = build_project_problem(resource_capacity=3)
    _VALIDATE.validate(problem)

    cpm_v = _VERIFY.verify(problem, select_strategy(problem, "cpm").solve(problem))
    pl_v = _VERIFY.verify(problem, select_strategy(problem, "priority_list").solve(problem))
    cpsat_v = _VERIFY.verify(problem, select_strategy(problem, "cp_sat").solve(problem))

    assert cpm_v.status == "invalid"  # 資源超過
    assert pl_v.status == "valid"
    assert cpsat_v.status == "valid"
    assert _plan(cpsat_v).makespan <= _plan(pl_v).makespan


def test_end_to_end_invalid_when_makespan_bound_violated() -> None:
    """makespan に厳しい上限 → 汎用 numeric_bound チェッカーが project 解に効く。"""
    problem = build_project_problem(resource_capacity=None)
    capped = problem.model_copy(
        update={
            "constraints": [
                NumericBoundConstraint(severity="hard", field="makespan", operator="<=", value=5)
            ]
        }
    )
    raw = select_strategy(capped).solve(capped)
    verified = _VERIFY.verify(capped, raw)
    assert verified.status == "invalid"
