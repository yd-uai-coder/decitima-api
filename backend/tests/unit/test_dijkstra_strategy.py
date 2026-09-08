"""作業単位 1-4: DijkstraStrategy。

Phase-0-9.md §1.1 のテスト例 + 禁止エッジ / 必須経由 / 非連結 / 再現性。
registry.py の DijkstraStrategy 行の有効化(進行ルール #15)もここで確認する。

Phase4にてdijkstra.pyの構成を変更したため再テスト->記法が変わったためエラー発生
"""

from tests.fixtures.optimization import build_route_problem

from app.algorithms.graph.dijkstra import DijkstraStrategy
from app.algorithms.registry import get_strategies
from app.domain.solutions.route_planner import RouteSolution
from app.domain.solutions.solution import CandidateSolution

# solve()を呼ぶためのインスタンス生成
# sol = _STRATEGY.solve(build_route_problem())　から
# build_route_problem(引数) -> OptimizationProblem
# 引数(forbidden, required)がconstraintsとしてsolveに渡る
# solve(problem: OptimizationProblem) -> エッジの連結 -> CandidateSolution
# _route(sol: CandidateSolution) -> RouteSolutionの流れ
_STRATEGY = DijkstraStrategy()


def _route(sol: CandidateSolution) -> RouteSolution:
    """assignments を RouteSolution に絞り込む(discriminated union の消費側の定石)。"""
    assert isinstance(sol.assignments, RouteSolution)
    return sol.assignments


def test_finds_shortest_path_without_constraints() -> None:
    # A-B-D-E = 2+1+2 = 5 が最短(禁止・必須なし)
    sol = _STRATEGY.solve(build_route_problem())
    assert sol.status == "valid"
    assert _route(sol).path_node_ids == ["A", "B", "D", "E"]
    assert _route(sol).total_weight == 5.0
    assert sol.metrics["total_weight"] == 5.0


def test_respects_forbidden_edge_and_required_node() -> None:
    # 橋 e_bd 禁止 + C 必須経由 → A-B-C-E = 9(Phase-0-2.md §7.1 の期待解)
    sol = _STRATEGY.solve(build_route_problem(forbidden=["e_bd"], required=["C"]))
    assert _route(sol).path_node_ids == ["A", "B", "C", "E"]
    assert _route(sol).path_edge_ids == ["e_ab", "e_bc", "e_ce"]
    assert _route(sol).total_weight == 9.0
    assert "e_bd" not in _route(sol).path_edge_ids
    assert "C" in _route(sol).path_node_ids

# 未連結のノードが存在することの確認(2つのforbiddenによりA->Eへの到達が不可能
def test_infeasible_when_goal_unreachable() -> None:
    sol = _STRATEGY.solve(build_route_problem(forbidden=["e_ce", "e_de"]))
    assert sol.status == "infeasible"
    assert _route(sol).path_node_ids == []

# 再現性の確認（複数回実施して順番が変わってはいけない）
def test_deterministic_same_input_same_output() -> None:
    p = build_route_problem(forbidden=["e_bd"], required=["C"])
    assert _STRATEGY.solve(p).model_dump() == _STRATEGY.solve(p).model_dump()

def test_produced_by_metadata_is_attached() -> None:
    # meta情報を拾ってくる
    sol = _STRATEGY.solve(build_route_problem())
    assert sol.produced_by.name == "dijkstra"
    assert sol.produced_by.implementation == "handwritten"
    assert sol.produced_by.family == "graph"


def test_dijkstra_registered_for_route_planning() -> None:
    # 1-4 で registry.py の import 行と REGISTRY エントリのコメントを外した結果、
    # route_planning から dijkstra を引ける(1-2 では機構をフェイクで検証済み)。
    assert "dijkstra" in [s.meta.name for s in get_strategies("route_planning")]
