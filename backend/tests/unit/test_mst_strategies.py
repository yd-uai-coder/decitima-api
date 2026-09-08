"""作業単位 5-4: network_design(MST)ストラテジー ── Kruskal / Prim / networkx。

対象 = 各 Strategy.solve(純粋)。ドライバ = このテスト関数。スタブ不要。

`test_network_design_end_to_end_pipeline` は 5-3 から移設 ── validate→select→solve→verify の
フルパイプラインは `registry["network_design"]` が埋まる 5-4 で初めて green になる(#15)。
"""

import pytest
from tests.fixtures.optimization import (
    build_disconnected_network_problem,
    build_network_problem,
)

from app.algorithms.graph.kruskal import KruskalStrategy
from app.algorithms.graph.networkx_mst import NetworkxMST
from app.algorithms.graph.prim import PrimStrategy
from app.domain.solutions.network_design import NetworkDesignSolution
from app.services.algorithm_selection import select_strategy
from app.services.validation import ProblemValidationService
from app.services.verification import SolutionVerificationService

_STRATEGIES = [KruskalStrategy(), PrimStrategy(), NetworkxMST()]
_IDS = [f"{s.meta.name}:{s.meta.implementation}" for s in _STRATEGIES]


def _sol(candidate) -> NetworkDesignSolution:
    assert isinstance(candidate.assignments, NetworkDesignSolution)
    return candidate.assignments


@pytest.mark.parametrize("strategy", _STRATEGIES, ids=_IDS)
def test_all_mst_strategies_agree_on_total_weight(strategy) -> None:
    sol = strategy.solve(build_network_problem())
    assert sol.status == "valid"
    assert _sol(sol).total_weight == 10.0  # 既知の MST コスト
    assert len(_sol(sol).selected_link_ids) == 4  # V - 1


@pytest.mark.parametrize("strategy", _STRATEGIES, ids=_IDS)
def test_mst_respects_required_and_forbidden(strategy) -> None:
    sol = strategy.solve(build_network_problem(required=["L_ac"], forbidden=["L_bc"]))
    picked = set(_sol(sol).selected_link_ids)
    assert "L_ac" in picked  # 必須
    assert "L_bc" not in picked  # 禁止


@pytest.mark.parametrize("strategy", _STRATEGIES, ids=_IDS)
def test_mst_infeasible_when_disconnected(strategy) -> None:
    sol = strategy.solve(build_disconnected_network_problem())
    assert sol.status == "infeasible"


def test_handwritten_mst_reports_ops_library_does_not() -> None:
    assert "_ops" in KruskalStrategy().solve(build_network_problem()).metrics
    assert "_ops" in PrimStrategy().solve(build_network_problem()).metrics
    assert "_ops" not in NetworkxMST().solve(build_network_problem()).metrics


def test_required_links_forming_cycle_is_infeasible() -> None:
    # L_ab + L_bc + L_ac の 3 本を必須にすると A-B-C で閉路 → 全域木にならない
    sol = KruskalStrategy().solve(build_network_problem(required=["L_ab", "L_bc", "L_ac"]))
    assert sol.status == "infeasible"


def test_network_design_end_to_end_pipeline() -> None:
    """validate → select_strategy → solve → verify が network_design で通る(専用 route 不要)。

    """
    problem = build_network_problem()
    ProblemValidationService().validate(problem)
    strategy = select_strategy(problem)
    raw = strategy.solve(problem)
    verified = SolutionVerificationService().verify(problem, raw)
    assert verified.status == "valid"
    assert verified.metrics["total_weight"] == 10.0
