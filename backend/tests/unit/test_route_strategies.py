"""作業単位 4-2 / 4-3 / 4-4 / 4-5: route_planning の新ストラテジーと共通の足回り。

対象 = 各 Strategy.solve(純粋)。ドライバ = このテスト関数。スタブ不要 ── solve は純粋
(DijkstraStrategy と同じ。外部依存を呼ばない。networkx は決定論的なのでスタブ不要)。
"""

import pytest
from tests.fixtures.optimization import (
    build_coord_route_problem,
    build_negative_cycle_route_problem,
    build_negative_route_problem,
    build_route_problem,
    build_scaled_route_problem,
)

from app.algorithms.graph.a_star import AStarStrategy
from app.algorithms.graph.bellman_ford import BellmanFordStrategy
from app.algorithms.graph.dijkstra import DijkstraStrategy
from app.algorithms.graph.networkx_shortest import NetworkxShortestPath
from app.algorithms.graph.waypoints import optimize_waypoint_order
from app.domain.problems.route_planner import RouteData, RouteEdge, RouteNode
from app.domain.solutions.route_planner import RouteSolution


def _path(sol) -> RouteSolution:
    assert isinstance(sol.assignments, RouteSolution)
    return sol.assignments


# ---------------------------------------------------------------------------
# Bellman-Ford(4-2)
# ---------------------------------------------------------------------------


def test_bellman_ford_uses_negative_edge_path() -> None:
    # S->A->B->T (2-4+3=1) が S->T 直行(5)より短い。Dijkstra は誤答するケース。
    sol = BellmanFordStrategy().solve(build_negative_route_problem())
    assert sol.status == "valid"
    assert _path(sol).path_node_ids == ["S", "A", "B", "T"]
    assert _path(sol).total_weight == 1.0


def test_dijkstra_refuses_negative_graph() -> None:
    sol = DijkstraStrategy().solve(build_negative_route_problem())
    assert sol.status == "infeasible"
    #　負変グラフの受け入れを有効化したため、negative_weightが返る
    assert sol.violations[0].constraint_kind == "negative_weight"


def test_bellman_ford_detects_negative_cycle() -> None:
    sol = BellmanFordStrategy().solve(build_negative_cycle_route_problem())
    assert sol.status == "infeasible"
    assert sol.violations[0].constraint_kind == "negative_cycle"


def test_negative_weight_needs_allow_negative_flag() -> None:
    with pytest.raises(ValueError, match="allow_negative"):
        RouteData(
            nodes=[RouteNode(id="a"), RouteNode(id="b")],
            edges=[RouteEdge(id="e", source="a", target="b", weight=-1)],
            start="a",
            goal="b",
        )


# ---------------------------------------------------------------------------
# A*(4-3)
# ---------------------------------------------------------------------------

# 重みの総和がA*とダイクストラで同じ
def test_a_star_matches_dijkstra_optimum() -> None:
    p = build_coord_route_problem()
    a = AStarStrategy().solve(p)
    d = DijkstraStrategy().solve(p)
    assert a.status == "valid"
    assert a.metrics["total_weight"] == d.metrics["total_weight"]

# ヒープホップ数がA*の方が少ない（ノードの展開数が減る）
def test_a_star_explores_fewer_nodes_with_heuristic() -> None:
    p = build_coord_route_problem()
    a = AStarStrategy().solve(p)
    d = DijkstraStrategy().solve(p)
    # goal と逆方向の寄り道クラスタを A* は pop しない
    assert a.metrics["_ops"] < d.metrics["_ops"]


def test_a_star_without_coords_equals_dijkstra() -> None:
    p = build_route_problem()  # 座標なし → h(n)=0 → Dijkstra に縮退、つまりaとdで結果が一致する。
    a = AStarStrategy().solve(p)
    d = DijkstraStrategy().solve(p)
    assert _path(a).path_node_ids == _path(d).path_node_ids


# ---------------------------------------------------------------------------
# 経由順最適化(4-4)(7-4)
# ---------------------------------------------------------------------------


def test_optimize_waypoint_order_reorders_for_shorter_total() -> None:
    """経由地の数 <= 8 の時
    Phase7では_exact_best関数として定義し、結果が壊れていない事を確認
    """
    # cost 表: 1D 直線 start=0, goal=10, 経由地 A=8, B=2。最適順は B, A
    positions = {"start": 0.0, "goal": 10.0, "A": 8.0, "B": 2.0}

    # optimize_waypoint_orderの第四引数に関数オブジェクトとして渡す
    # cost関数の引数と戻り値型は
    # type SegmentCost = Callable[[str, str], float | None]
    def cost(a: str, b: str) -> float | None:
        return abs(positions[a] - positions[b])

    order = optimize_waypoint_order("start", "goal", ["A", "B"], cost)

    # 順序最適化の結果確認: Bの方が重みが低いので前
    assert order == ["start", "B", "A", "goal"]


def test_optimize_waypoint_order_returns_none_when_disconnected() -> None:
    # optimize_waypoint_orderの第四引数は必ずNoneを返す ->　optimize_waypoint_order関数がNoneを返す
    assert optimize_waypoint_order("s", "g", ["w"], lambda _a, _b: None) is None


# Phase4段階での検証->Phase7-4でwaypoints.pyの変更に伴い失効
# def test_optimize_waypoint_order_keeps_given_order_when_too_many() -> None:
#     required = [f"w{i}" for i in range(9)]  # > _MAX_EXACT

#     # optimize_waypoint_orderの第四引数costは必ず1.0を返す
#     # len(required)>8のため、関数の実行前にreturnされる(順序変更なし)
#     # costの実引数は型ヒントを守っていればよい
#     order = optimize_waypoint_order("s", "g", required, lambda _a, _b: 1.0)
#     assert order == ["s", *required, "g"] #これが想定されるbest_order

def test_optimize_waypoint_order_approx_returns_none_when_disconnected() -> None:
    """m > _MAX_EXACT で近似(_approx_best)に入っても、どの順でも繋がらないなら None。

    _exact_best の None は全順列を試した確定判定、_approx_best の None は最近傍 + 2-opt が
    組んだ最終 seq が繋がらなかったこと ── コードベースの cost(全点対距離由来)では
    「別成分にまたがる」が両者共通のトリガーになり、結果は一致する。
    """
    required = [f"w{i}" for i in range(9)]  # > _MAX_EXACT
    assert optimize_waypoint_order("s", "g", required, lambda _a, _b: None) is None


def test_optimize_waypoint_order_approximates_when_too_many() -> None:
    """m > _MAX_EXACT: 最近傍 + 2-opt の近似(Phase 7-4)。

    Phase 4-6 まで: `assert order == ["s", *required, "g"]`(与えられた順のまま)。
    Phase 7-4 から: 近似で並べ替える。厳密性は保証しないが「全経由地を訪れ、
    与えられた順より悪くない」ことは満たす。
    """
    required = [f"w{i}" for i in range(9)]  # > _MAX_EXACT
    order = optimize_waypoint_order("s", "g", required, lambda _a, _b: 1.0)
    assert order is not None #到達不可能でなければNoneは返らない
    assert set(order) == {"s", "g", *required}  # 全部訪れる
    assert len(order) == len(set(order))  # 重複なし
    assert order[0] == "s" and order[-1] == "g"



def test_optimize_waypoint_order_approx_beats_given_order() -> None:
    """非一様なコストなら、近似は「与えられた順」より短い経路を見つける。"""
    # 1D 直線上に並べ、わざと交互(遠い→近い→遠い…)の順で渡す
    positions = {"s": 0.0, "g": 100.0}
    positions.update({f"w{i}": float(i * 5) for i in range(10)})  # w0=0 .. w9=45
    given = ["w0", "w9", "w1", "w8", "w2", "w7", "w3", "w6", "w4"]  # > 8、ジグザグ

    def cost(a: str, b: str) -> float:
        return abs(positions[a] - positions[b])

    approx = optimize_waypoint_order("s", "g", given, cost)
    assert approx is not None
    given_total = sum(cost(a, b) for a, b in zip(["s", *given, "g"], [*given, "g"], strict=False))
    approx_total = sum(cost(a, b) for a, b in zip(approx, approx[1:], strict=False))
    assert approx_total <= given_total


def test_strategies_visit_all_required_regardless_of_input_order() -> None:
    forward = DijkstraStrategy().solve(build_route_problem(required=["B", "C"]))
    reverse = DijkstraStrategy().solve(build_route_problem(required=["C", "B"]))
    assert set(_path(forward).path_node_ids) >= {"A", "B", "C", "E"}

    #requiredの要素順を替えても結果が一致する事を確認（順序最適化が活きている）
    assert _path(forward).total_weight == _path(reverse).total_weight


# ---------------------------------------------------------------------------
# networkx トラック + オラクル(4-5)
# ---------------------------------------------------------------------------


def test_networkx_matches_handwritten_dijkstra_property() -> None:
    """手実装 Dijkstra == networkx shortest_path(別実装オラクル)。"""
    handwritten = DijkstraStrategy()
    library = NetworkxShortestPath()
    for seed in range(30):
        problem = build_scaled_route_problem(12, seed=seed)
        hw = handwritten.solve(problem)
        lib = library.solve(problem)
        # networkXを利用した計算とdijkstraでの結果が一致することの確認
        assert hw.status == lib.status
        if hw.status == "valid":
            assert hw.metrics["total_weight"] == pytest.approx(lib.metrics["total_weight"])


def test_networkx_entry_has_no_ops() -> None:
    sol = NetworkxShortestPath().solve(build_route_problem())
    assert "_ops" not in sol.metrics  # ライブラリトラックは操作回数を出せない
