"""深さ優先探索(プリミティブ)。
DFS = Depth-First Search
まず一つの枝を奥まで進む。
経路の有無・連結判定・訪問順。再帰で書く。
無重みグラフの「最短」は保証しない(それは BFS)。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping

AdjacencyList = Mapping[str, Iterable[str]]


def dfs_preorder(adjacency: AdjacencyList, start: str) -> list[str]:
    """start から深さ優先で訪問したノードを、訪問順(行きがけ)に並べて返す。"""
    visited: set[str] = set()
    order: list[str] = []

    def _visit(node: str) -> None:
        # visitedはset():重複禁止なので、訪問済みは追加されない(空振り)
        visited.add(node)
        order.append(node)
        for nxt in adjacency.get(node, ()):
            # nxtが未訪問ならさらに深いノードへ進む(再帰)
            if nxt not in visited:
                _visit(nxt)
    # 探索開始
    _visit(start)
    return order


def dfs_has_path(adjacency: AdjacencyList, start: str, goal: str) -> bool:
    """start から goal へ到達できるか(経路の存在のみ。最短性は問わない)。"""
    visited: set[str] = set()

    def _visit(node: str) -> bool:
        if node == goal:
            return True
        visited.add(node)
        # 隣接ノードのいずれかから goal に届けば True
        return any(nxt not in visited and _visit(nxt) for nxt in adjacency.get(node, ()))

    return _visit(start)
