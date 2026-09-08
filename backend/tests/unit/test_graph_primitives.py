"""作業単位 4-1: グラフプリミティブ(adjacency + segments + waypoints ── route スライス)。

対象 = 純粋関数。ドライバ = このテスト関数。
スタブ = `plan_route` に渡す区間ソルバ(`segment_fn`)と `optimize_waypoint_order` に渡す
コスト関数を**フェイク**にする ── segments.py は「区間の解き方」を注入できる設計なので、
実グラフ・実 Dijkstra 無しで連結ロジックだけをテストできる(`Phase-4-1.md` §2)。

この 3 ファイル(adjacency / segments / waypoints)は 4-1 で新規作成する。import が
`segments` → `waypoints` と辿るので、どれか 1 つでも写経漏れがあると collection が赤になる。
`dijkstra.py` のリファクタ(4-1)の回帰は**ここで統合スモークを踏み**(`test_dijkstra_solve_*`)、
加えて Phase 1 の `test_dijkstra_strategy.py` も再実行する(進行のルール #16)。

`UnionFind` は Phase 5-1、`connectivity` / `build_link_adjacency` は Phase 5-3 でテストする。
"""

from collections.abc import Mapping

from tests.fixtures.optimization import (
    build_disconnected_network_problem,
    build_network_problem,
    build_route_problem,
)

from app.algorithms.graph.adjacency import (
    build_adjacency,
    has_negative_weight,
    plain_adjacency,
    build_link_adjacency,

)
from app.algorithms.graph.connectivity import all_nodes_connected, forms_spanning_tree

from app.algorithms.graph.dijkstra import DijkstraStrategy
from app.algorithms.graph.segments import (
    Segment,
    collect_route_constraints,
    plan_route,
    route_solution,
)
from app.algorithms.graph.waypoints import optimize_waypoint_order
from app.domain.problems.network_design import NetworkDesignData
from app.domain.problems.route_planner import RouteData
from app.domain.solutions.route_planner import RouteSolution
from app.domain.solutions.solution import AlgorithmMeta

_META = AlgorithmMeta(name="fake", family="graph", implementation="handwritten")


def _route_data(problem) -> RouteData:
    data = problem.data
    assert isinstance(data, RouteData)  # 判別可能ユニオンの消費側の定石
    return data

def _network_data(problem) -> NetworkDesignData:
    data = problem.data
    assert isinstance(data, NetworkDesignData)
    return data


# ===========================================================================
# route(Phase 4-1)── 以下はリファクタ追従の番人。assertion は 4-1 のまま
# ===========================================================================

# ---------------------------------------------------------------------------
# adjacency.py
# ---------------------------------------------------------------------------


def test_build_adjacency_undirected_adds_reverse_edge() -> None:
    data = _route_data(build_route_problem())
    adj = build_adjacency(data, forbidden_edge_ids=set())
    # e_ab は無向 → A に B、B に A の両方向が張られる
    assert ("B", "e_ab", 2.0) in adj["A"]
    assert ("A", "e_ab", 2.0) in adj["B"]


def test_build_adjacency_skips_forbidden() -> None:
    data = _route_data(build_route_problem())
    adj = build_adjacency(data, forbidden_edge_ids={"e_bd"})
    assert all(eid != "e_bd" for edges in adj.values() for _n, eid, _w in edges)


def test_plain_adjacency_drops_weight_and_id() -> None:
    adj = build_adjacency(_route_data(build_route_problem()), set())
    plain = plain_adjacency(adj)
    assert set(plain["A"]) == {"B"}


def test_has_negative_weight() -> None:
    assert has_negative_weight({"a": [("b", "e", -1.0)]})
    assert not has_negative_weight({"a": [("b", "e", 1.0)]})


# ---------------------------------------------------------------------------
# segments.py ── 区間ソルバをフェイクにして連結ロジックだけ見る
# ---------------------------------------------------------------------------


def _fake_segment_fn(table: Mapping[tuple[str, str], Segment | None]):
    """区間ソルバのフェイク。引いた (a, b) を table から返す。ops は 1 回呼ぶごとに 1。"""

    def fn(a: str, b: str) -> tuple[Segment | None, int]:
        return table.get((a, b)), 1

    return fn


def test_plan_route_stitches_segments_and_dedupes_boundary() -> None:
    table = {
        ("A", "C"): Segment(["A", "B", "C"], ["e_ab", "e_bc"], 5.0),
        ("C", "E"): Segment(["C", "E"], ["e_ce"], 4.0),
    }
    seg, ops = plan_route("A", "E", ["C"], _fake_segment_fn(table))
    assert seg is not None
    # 区間の境界ノード C は 1 つに畳まれる
    assert seg.node_ids == ["A", "B", "C", "E"]
    assert seg.edge_ids == ["e_ab", "e_bc", "e_ce"]
    assert seg.weight == 9.0
    # 2 区間を解いた(順序探索と連結で同じ区間は 1 度だけ ── _SegmentCache)
    assert ops == 2


def test_plan_route_infeasible_when_a_segment_is_none() -> None:
    seg, ops = plan_route("A", "E", [], _fake_segment_fn({("A", "E"): None}))
    assert seg is None
    assert ops == 1


def test_collect_route_constraints_reads_forbidden_and_required() -> None:
    forbidden, required = collect_route_constraints(
        build_route_problem(forbidden=["e_bd"], required=["C"])
    )
    assert forbidden == {"e_bd"}
    assert required == ["C"]


def test_route_solution_none_segment_is_infeasible() -> None:
    sol = route_solution(None, 3, _META)
    assert sol.status == "infeasible"
    assert sol.metrics == {"_ops": 3.0}


# ---------------------------------------------------------------------------
# waypoints.py ── 骨格(4-4 で全順列探索を深掘り)
# ---------------------------------------------------------------------------


def test_optimize_waypoint_order_no_waypoints_is_start_goal() -> None:
    assert optimize_waypoint_order("A", "E", [], lambda _a, _b: 1.0) == ["A", "E"]


def test_optimize_waypoint_order_single_waypoint_keeps_it() -> None:
    assert optimize_waypoint_order("A", "E", ["C"], lambda _a, _b: 1.0) == ["A", "C", "E"]


# ---------------------------------------------------------------------------
# dijkstra.py の 4-1 リファクタ ── 統合スモーク
# ---------------------------------------------------------------------------


def test_dijkstra_solve_still_works_after_segments_refactor() -> None:
    """4-1 で dijkstra.py の内部を segments.py 経由に変えた ── その連鎖
    (adjacency → segments → waypoints → _dijkstra_segment → _reconstruct)が繋がっているか。

    `_dijkstra_segment` の末尾 `return _reconstruct(prev, start, goal, dist[goal]), pops` で
    return / `, pops` / `dist[goal]` のどれかを写し損なうと、`_dijkstra_segment` が `None` を返し
    `TypeError: cannot unpack non-iterable NoneType object`(segments.py の `_SegmentCache`)で
    ここが赤くなる ── その時は dijkstra.py の `_dijkstra_segment` の末尾を見る。
    """
    sol = DijkstraStrategy().solve(build_route_problem())
    assert sol.status == "valid"
    assert isinstance(sol.assignments, RouteSolution)
    assert sol.assignments.path_node_ids == ["A", "B", "D", "E"]
    assert sol.assignments.total_weight == 5.0


# ===========================================================================
# network(Phase 5-3)── build_link_adjacency + connectivity の写経ミスの第一の番人
# ===========================================================================


def test_build_link_adjacency_is_always_undirected() -> None:
    data = _network_data(build_network_problem())
    adj = build_link_adjacency(data, forbidden_link_ids=set())
    assert ("B", "L_ab", 1.0) in adj["A"]
    assert ("A", "L_ab", 1.0) in adj["B"]


def test_build_link_adjacency_skips_forbidden() -> None:
    data = _network_data(build_network_problem())
    adj = build_link_adjacency(data, forbidden_link_ids={"L_ab"})
    assert all(lid != "L_ab" for edges in adj.values() for _n, lid, _w in edges)


def test_all_nodes_connected() -> None:
    ok = _network_data(build_network_problem())
    adj_ok = build_link_adjacency(ok, set())
    assert all_nodes_connected((n.id for n in ok.nodes), adj_ok)

    bad = _network_data(build_disconnected_network_problem())
    adj_bad = build_link_adjacency(bad, set())
    assert not all_nodes_connected((n.id for n in bad.nodes), adj_bad)


def test_forms_spanning_tree() -> None:
    nodes = ["A", "B", "C", "D"]
    # 3 本で連結 → 木
    assert forms_spanning_tree(nodes, [("A", "B"), ("B", "C"), ("C", "D")])
    # 3 本だが閉路 + 孤立(D) → 木でない
    assert not forms_spanning_tree(nodes, [("A", "B"), ("B", "C"), ("C", "A")])
    # 辺数が V-1 でない
    assert not forms_spanning_tree(nodes, [("A", "B"), ("B", "C")])
