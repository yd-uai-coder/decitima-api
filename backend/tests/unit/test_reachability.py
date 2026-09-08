"""作業単位 2-2: route_reachable(app/algorithms/graph/reachability.py)。

純粋関数。スタブ不要 ── RouteData を手で組んで直接呼ぶ。
"""

from app.algorithms.graph.reachability import route_reachable
from app.domain.problems.route_planner import RouteData, RouteEdge, RouteNode


def _data(edges: list[RouteEdge], *, start: str = "A", goal: str = "E") -> RouteData:
    return RouteData(
        nodes=[RouteNode(id=n) for n in ["A", "B", "C", "D", "E"]],
        edges=edges,
        start=start,
        goal=goal,
    )


_EDGES = [
    RouteEdge(id="e_ab", source="A", target="B", weight=2),
    RouteEdge(id="e_bc", source="B", target="C", weight=3),
    RouteEdge(id="e_bd", source="B", target="D", weight=1),
    RouteEdge(id="e_ce", source="C", target="E", weight=4),
    RouteEdge(id="e_de", source="D", target="E", weight=2),
]

# 禁止エッジなしでエッジ連結を行い、到達可能なことをチェック
def test_reachable_with_no_forbidden() -> None:
    assert route_reachable(_data(_EDGES), set()) is True

# 禁止エッジありで到達不可能をチェック
def test_unreachable_when_all_paths_to_goal_forbidden() -> None:
    # e_ce と e_de を禁止すると E に入る辺が無くなる
    assert route_reachable(_data(_EDGES), {"e_ce", "e_de"}) is False

# 禁止エッジありで到達可能をチェック
def test_still_reachable_when_one_of_two_paths_forbidden() -> None:
    # e_bd を禁止しても A-B-C-E で到達可能
    assert route_reachable(_data(_EDGES), {"e_bd"}) is True


# startと禁止エッジありで到達可能をチェック
def test_isolated_start_is_unreachable() -> None:
    # start=D、D に触れる辺(e_bd / e_de)を両方禁止 → D は孤立
    assert route_reachable(_data(_EDGES, start="D"), {"e_bd", "e_de"}) is False


# startと禁止エッジありで到達不可能をチェック
def test_directed_edge_wrong_way_is_unreachable() -> None:
    # E→D の一方向辺だけ → A から E には行けない
    one_way = [RouteEdge(id="e_ed", source="E", target="D", weight=1, directed=True)]
    assert route_reachable(_data(one_way), set()) is False
