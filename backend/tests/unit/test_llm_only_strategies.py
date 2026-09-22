"""作業単位 14-2/14-3/14-4: `app/algorithms/llm/` の6 `LlmOnly*Strategy`。

テスト対象 / ドライバ / スタブ:
- 対象: 各 `LlmOnly*Strategy.solve`
- ドライバ: このテスト関数
- スタブ: `FakeLLM`(各ドメインモジュールの `get_gemini_llm` を monkeypatch する ──
  Phase 12/13 と同じ「呼び出し元モジュールの名前空間を差し替える」形)。実 LLM は呼ばない。

**この Phase の設計の核**: LLM には既存の `RouteSolution`/`ShiftSolution`/… と全く同じ
スキーマを出力させる。変換コードを書かないので、正しい構造を返せば既存
`SolutionVerificationService` がそのまま valid とし、嘘の派生値(total_weight 等)を
返せば既存の構造検証がそのまま hard violation として検出する ── 手実装 Algorithm と
**全く同じ検証コード**で LLM 解を検証できることを、6ドメイン + 1つの「嘘」ケースで確認する。
"""

from __future__ import annotations

import pytest
from pydantic import BaseModel
from tests.fixtures.fake_llm import FakeLLM
from tests.fixtures.optimization import (
    build_logistics_problem,
    build_network_problem,
    build_project_problem,
    build_route_problem,
    build_shift_problem,
    build_travel_problem,
)

from app.algorithms.llm import (
    logistics_llm,
    network_llm,
    project_llm,
    route_llm,
    shift_llm,
    travel_llm,
)
from app.algorithms.llm.logistics_llm import LlmOnlyLogisticsStrategy
from app.algorithms.llm.network_llm import LlmOnlyNetworkStrategy
from app.algorithms.llm.project_llm import LlmOnlyProjectStrategy
from app.algorithms.llm.route_llm import LlmOnlyRouteStrategy
from app.algorithms.llm.shift_llm import LlmOnlyShiftStrategy
from app.algorithms.llm.travel_llm import LlmOnlyTravelStrategy
from app.domain.solutions.logistics import LogisticsSolution, VehicleRoute
from app.domain.solutions.network_design import NetworkDesignSolution
from app.domain.solutions.project_manager import ProjectSolution, ScheduledTask
from app.domain.solutions.route_planner import RouteSolution
from app.domain.solutions.shift_scheduler import ShiftSolution
from app.domain.solutions.travel_planner import TravelSolution
from app.services.verification import SolutionVerificationService


def _patch(monkeypatch: pytest.MonkeyPatch, module: object, structured: BaseModel) -> None:
    monkeypatch.setattr(module, "get_gemini_llm", lambda **_: FakeLLM(structured=structured))


# (Phase 14-2) route/network(グラフ系)。meta.family == "llm" は6クラス共通
# (AlgorithmMeta.family の Phase 14-1 拡張)。


def test_route_llm_only_solves_to_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    problem = build_route_problem()  # A -> B -> D -> E が最短(weight=5)
    solution = RouteSolution(
        path_node_ids=["A", "B", "D", "E"],
        path_edge_ids=["e_ab", "e_bd", "e_de"],
        total_weight=5,
    )
    _patch(monkeypatch, route_llm, solution)

    strategy = LlmOnlyRouteStrategy()
    assert strategy.meta.family == "llm"
    candidate = strategy.solve(problem)
    verified = SolutionVerificationService().verify(problem, candidate)

    assert verified.status == "valid"
    assert verified.violations == []


def test_route_llm_only_lie_about_total_weight_is_caught(monkeypatch: pytest.MonkeyPatch) -> None:
    """構造は正しいが total_weight が嘘 ── 既存の構造検証がそのまま hard violation にする
    (Phase 14 の「検証可能性」の実演: LLM の出力も Algorithm と同じ検証コードにさらされる)。"""
    problem = build_route_problem()
    lying_solution = RouteSolution(
        path_node_ids=["A", "B", "D", "E"],
        path_edge_ids=["e_ab", "e_bd", "e_de"],
        total_weight=100,  # 実際のエッジ合計は 5
    )
    _patch(monkeypatch, route_llm, lying_solution)

    candidate = LlmOnlyRouteStrategy().solve(problem)
    verified = SolutionVerificationService().verify(problem, candidate)

    assert verified.status == "invalid"
    assert any(v.constraint_kind == "route_structure" for v in verified.violations)


def test_network_llm_only_solves_to_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    problem = build_network_problem()
    solution = NetworkDesignSolution(
        selected_link_ids=["L_ab", "L_bc", "L_cd", "L_be"], total_weight=10
    )
    _patch(monkeypatch, network_llm, solution)

    candidate = LlmOnlyNetworkStrategy().solve(problem)
    verified = SolutionVerificationService().verify(problem, candidate)

    assert verified.status == "valid"
    assert verified.violations == []


# (Phase 14-3) shift/project(スケジューリング系)。
def test_shift_llm_only_solves_to_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    problem = build_shift_problem()
    # tanaka は 2026-09-02(s3/s4)が希望休(soft制約)なので、s1 だけに割り当てて避ける。
    solution = ShiftSolution(
        assignments={
            "s1": ["tanaka"],
            "s2": ["sato"],
            "s3": ["sato"],
            "s4": ["sato"],
        }
    )
    _patch(monkeypatch, shift_llm, solution)

    candidate = LlmOnlyShiftStrategy().solve(problem)
    verified = SolutionVerificationService().verify(problem, candidate)

    assert verified.status == "valid"
    assert verified.violations == []


def test_project_llm_only_solves_to_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    problem = build_project_problem(resource_capacity=None)  # 資源制約なしの純粋 CPM
    solution = ProjectSolution(
        task_order=["A", "B", "C", "D", "E"],
        schedule=[
            ScheduledTask(task_id="A", start=0, finish=3, slack=0),
            ScheduledTask(task_id="B", start=0, finish=2, slack=3),
            ScheduledTask(task_id="C", start=3, finish=7, slack=0),
            ScheduledTask(task_id="D", start=2, finish=4, slack=3),
            ScheduledTask(task_id="E", start=7, finish=8, slack=0),
        ],
        critical_path=["A", "C", "E"],
        makespan=8,
    )
    _patch(monkeypatch, project_llm, solution)

    candidate = LlmOnlyProjectStrategy().solve(problem)
    verified = SolutionVerificationService().verify(problem, candidate)

    assert verified.status == "valid"
    assert verified.violations == []


# (Phase 14-4) travel/logistics(最適化系)。
def test_travel_llm_only_solves_to_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    problem = build_travel_problem()
    # 何も訪問しない(予算・時間を使わない)最も単純な valid 解 ── strategy が既存
    # スキーマをそのまま検証に通せることの確認が目的なので、最適性は問わない。
    solution = TravelSolution(
        selected_place_ids=[], visit_order=[], total_value=0, total_cost=0, total_time=0
    )
    _patch(monkeypatch, travel_llm, solution)

    candidate = LlmOnlyTravelStrategy().solve(problem)
    verified = SolutionVerificationService().verify(problem, candidate)

    assert verified.status == "valid"
    assert verified.violations == []





def test_logistics_llm_only_solves_to_valid(monkeypatch: pytest.MonkeyPatch) -> None:
    problem = build_logistics_problem()
    solution = LogisticsSolution(
        routes=[
            VehicleRoute(vehicle_id="V1", stop_ids=["P1", "P2"], distance=9),
            VehicleRoute(vehicle_id="V2", stop_ids=["P3"], distance=12),
        ],
        total_distance=21,
    )
    _patch(monkeypatch, logistics_llm, solution)

    candidate = LlmOnlyLogisticsStrategy().solve(problem)
    verified = SolutionVerificationService().verify(problem, candidate)

    assert verified.status == "valid"
    assert verified.violations == []
