"""作業単位 3-2: BruteForceRouteStrategy(正解オラクル)。

fixture グラフでの厳密性 + 「Dijkstra == BruteForce」プロパティ(seed を振って回す)。
対象は純粋なので**スタブ不要**。ドライバはこのテスト関数 + `build_scaled_route_problem`。

Dijkstraと結果が一致するため、test_dijkstra_strategy.pyと共通のテスト内容を実施
"""

from tests.fixtures.optimization import build_route_problem, build_scaled_route_problem

from app.algorithms.graph.dijkstra import DijkstraStrategy
from app.algorithms.optimization.brute_force import BruteForceRouteStrategy
from app.algorithms.registry import get_strategies
from app.domain.solutions.route_planner import RouteSolution
from app.domain.solutions.solution import CandidateSolution

# solve()を呼ぶためのインスタンス生成
# sol = _STRATEGY.solve(build_route_problem())　から
# build_route_problem(引数) -> OptimizationProblem
# 引数(forbidden, required)がconstraintsとしてsolveに渡る
# solve(problem: OptimizationProblem) -> エッジの連結 -> CandidateSolution
# _route(sol: CandidateSolution) -> RouteSolutionの流れ
_BRUTE = BruteForceRouteStrategy()
_DIJKSTRA = DijkstraStrategy()


def _route(sol: CandidateSolution) -> RouteSolution:
    assert isinstance(sol.assignments, RouteSolution)
    return sol.assignments


def test_finds_true_shortest_path() -> None:
    # 禁止・必須なし → A-B-D-E = 5(Dijkstra と同じ)
    sol = _BRUTE.solve(build_route_problem())
    assert sol.status == "valid"
    assert _route(sol).path_node_ids == ["A", "B", "D", "E"]
    assert _route(sol).total_weight == 5.0
    assert _route(sol).total_weight == 5.0
    assert sol.metrics["total_weight"] == 5.0


def test_respects_forbidden_and_required() -> None:
    # 橋 e_bd 禁止 + C 必須経由 → A-B-C-E = 9(Phase-0-2.md §7.1 の期待解)
    sol = _BRUTE.solve(build_route_problem(forbidden=["e_bd"], required=["C"]))
    assert _route(sol).path_node_ids == ["A", "B", "C", "E"]
    assert _route(sol).path_edge_ids == ["e_ab", "e_bc", "e_ce"]
    assert _route(sol).total_weight == 9.0
    assert "e_bd" not in _route(sol).path_edge_ids
    assert "C" in _route(sol).path_node_ids

# 未連結のノードが存在することの確認(2つのforbiddenによりA->Eへの到達が不可能
def test_infeasible_when_disconnected() -> None:
    sol = _BRUTE.solve(build_route_problem(forbidden=["e_ce", "e_de"]))
    assert sol.status == "infeasible"
    assert _route(sol).path_node_ids == []

# 再現性の確認（複数回実施して順番が変わってはいけない）
def test_deterministic_same_input_same_output() -> None:
    p = build_route_problem(forbidden=["e_bd"], required=["C"])
    assert _BRUTE.solve(p).model_dump() == _BRUTE.solve(p).model_dump()


def test_ops_counted_with_meta() -> None:
    sol = _BRUTE.solve(build_route_problem())
    assert sol.metrics["_ops"] > 0.0
    # meta情報を拾ってくる
    assert sol.produced_by.name == "brute_force"
    assert sol.produced_by.implementation == "handwritten"
    assert sol.produced_by.family == "optimization"


# 再現性の確認（複数回実施して順番が変わってはいけない）
def test_deterministic_same_input_same_output() -> None:
    p = build_route_problem(forbidden=["e_bd"], required=["C"])
    assert _BRUTE.solve(p).model_dump() == _BRUTE.solve(p).model_dump()


def test_registered_for_route_planning() -> None:
        # 1-4 で registry.py の import 行と REGISTRY エントリのコメントを外した結果、
    # route_planning から brute_force を引ける(1-2 では機構をフェイクで検証済み)。
    assert "brute_force" in [s.meta.name for s in get_strategies("route_planning")]


def test_matches_dijkstra_on_random_graphs() -> None:
    """オラクル: 小さな連結グラフでは Dijkstra の最短距離 = 全探索の最短距離。"""
    for seed in range(50):
        problem = build_scaled_route_problem(6, seed=seed) #ノード数6の連結グラフ生成
        d = _DIJKSTRA.solve(problem)
        b = _BRUTE.solve(problem)

        # 2つのアルゴリズムで結果が一致する事の確認
        assert d.status == "valid" and b.status == "valid"
        assert _route(d).total_weight == _route(b).total_weight, f"seed={seed}"
