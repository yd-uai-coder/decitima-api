"""作業単位 5-3: network_design の配線(スキーマ / semantic / 構造検証 / 制約チェッカー)。

対象 = 純粋な値オブジェクト・純粋関数。ドライバ = このテスト関数。スタブ不要。

validate→select→solve→verify のフルパイプライン統合テストは 5-4
(`test_mst_strategies.py::test_network_design_end_to_end_pipeline`)── `registry["network_design"]`
が Kruskal / Prim で埋まって初めて green になるため。
"""

import pytest
from pydantic import ValidationError
from tests.fixtures.optimization import (
    build_network_problem,
    build_network_solution,
)

from app.domain.constraints.forbidden import check_forbidden
from app.domain.constraints.required_inclusion import check_required_inclusion
from app.domain.problems.network_design import NetworkDesignData
from app.domain.problems.problem import (
    ForbiddenConstraint,
    OptimizationProblem,
    RequiredInclusionConstraint,
)
from app.domain.problems.semantic import SEMANTIC_CHECKS
from app.domain.solutions.network_design import NetworkDesignSolution
from app.domain.solutions.structure import structural_verify, verify_network_structure
from app.services.validation import ProblemValidationService
from app.services.verification import SolutionVerificationService


def test_optimization_problem_accepts_network_design() -> None:
    problem = build_network_problem()
    assert problem.problem_type == "network_design"
    # 判別可能ユニオンが正しく解決されている
    assert problem.data.problem_type == "network_design"


def test_problem_type_data_mismatch_is_rejected() -> None:
    with pytest.raises(ValidationError):
        OptimizationProblem(
            problem_type="route_planning",
            objectives=[],
            data=build_network_problem().data,
        )


def test_semantic_check_registered_for_network_design() -> None:
    assert "network_design" in SEMANTIC_CHECKS
    names = {c.__name__ for c in SEMANTIC_CHECKS["network_design"]}
    assert names == {"check_network_link_endpoints", "check_network_has_links"}


def test_validation_passes_for_connected_network() -> None:
    ProblemValidationService().validate(build_network_problem())  # 例外が飛ばなければ OK


def test_validation_rejects_disconnected_after_forbidden() -> None:
    from app.services.errors import InfeasibleProblemError

    problem = build_network_problem(forbidden=["L_bc", "L_ac", "L_ab", "L_ae", "L_be"])
    with pytest.raises(InfeasibleProblemError):
        ProblemValidationService().validate(problem)


def test_verify_network_structure_pure_predicates() -> None:
    data = build_network_problem().data
    assert isinstance(data, NetworkDesignData)
    good = build_network_solution(["L_ab", "L_bc", "L_cd", "L_be"], 10.0)
    assert isinstance(good.assignments, NetworkDesignSolution)
    assert verify_network_structure(data, good.assignments) == []

    wrong = build_network_solution(["L_ab", "L_bc", "L_cd", "L_be"], 999.0)
    assert isinstance(wrong.assignments, NetworkDesignSolution)
    kinds = [v.constraint_kind for v in verify_network_structure(data, wrong.assignments)]
    assert "network_structure" in kinds


def test_verification_flags_non_spanning_selection() -> None:
    problem = build_network_problem()
    # 4 本だが閉路 (A-B-C-A) を含み D が孤立
    bad = build_network_solution(["L_ab", "L_bc", "L_ac", "L_be"], 12.0)
    verified = SolutionVerificationService().verify(problem, bad)
    assert verified.status == "invalid"
    assert any(v.constraint_kind == "network_structure" for v in verified.violations)


def test_structural_verify_dispatches_network() -> None:
    problem = build_network_problem()
    sol = build_network_solution(["L_ab", "L_bc", "L_cd", "L_be"], 10.0)
    violations, extra = structural_verify(problem, sol)
    assert violations == [] and extra == {}


def test_forbidden_and_required_checkers_work_on_network_solution() -> None:
    problem = build_network_problem()
    sol = build_network_solution(["L_ab", "L_bc", "L_cd", "L_be"], 10.0)

    forbidden = ForbiddenConstraint(severity="hard", items=["L_bc"])
    assert check_forbidden(forbidden, problem, sol) is not None

    required = RequiredInclusionConstraint(severity="hard", items=["L_ac"])
    v = check_required_inclusion(required, problem, sol)
    assert v is not None and v.detail["missing"] == ["L_ac"]
