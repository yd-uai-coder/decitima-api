"""幅優先探索(プリミティブ)。
BFS = Breadth-First Search
まず同じ深さにあるノードを全部見る -> 次のノードへ
無重みグラフの最短経路・到達可能性。
"""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable, Mapping

# 隣接リスト: node_id -> 隣接 node_id の並び(無重み)
AdjacencyList = Mapping[str, Iterable[str]]


def bfs_distances(adjacency: AdjacencyList, start: str) -> dict[str, int]:
    """start からの各ノードへの最短ホップ数を返す。到達不能なノードは含めない。"""
    distances: dict[str, int] = {start: 0}
    queue: deque[str] = deque([start])

    # queueに要素が存在する限り繰り返す
    while queue:
        # dequeの左端（先頭）の要素を取り出して削除する
        node = queue.popleft()

        # node をキーとして検索し、存在すればその値(タプル)を返し、存在しなければ空のタプル () を返す
        for nxt in adjacency.get(node, ()):
            # 未訪問なら「今のノードの距離 + 1」で確定(BFS なので初回訪問が最短)
            # 訪問済みなら処理を行わず、次のループへ
            if nxt not in distances:
                distances[nxt] = distances[node] + 1
                queue.append(nxt)

    #queueが空になり、ループが終了した時点でのdistanceの値 : dict[str, int]
    return distances


# bfs_distancesの戻り値：dict のキーだけ取り、距離の値は捨てる
def reachable_nodes(adjacency: AdjacencyList, start: str) -> set[str]:
    """start から到達できるノード集合。route Validation の連結性チェックに使う。"""

    return set(bfs_distances(adjacency, start))


def bfs_shortest_path(adjacency: AdjacencyList, start: str, goal: str) -> list[str] | None:
    """start から goal までの無重み最短経路(ノード列)。到達不能なら None。"""
    if start == goal:
        return [start]
    # parent[n] = BFS 木で n に最初に到達したときの1つ前のノード
    parent: dict[str, str] = {}
    visited: set[str] = {start}
    queue: deque[str] = deque([start])
    while queue:
        node = queue.popleft()
        for nxt in adjacency.get(node, ()):
            if nxt in visited:
                # 訪問済みなら以降の処理をスキップして次のforループへ
                continue
            visited.add(nxt)
            parent[nxt] = node
            if nxt == goal:
                # goalに到達したら経路を記録する。
                return _reconstruct(parent, start, goal)
            # 未訪問且つgoalに到達していない探索元にnxtを追加する。
            queue.append(nxt)

    # 到達不可能の場合はNoneを返す
    return None

#経路の記録
def _reconstruct(parent: Mapping[str, str], start: str, goal: str) -> list[str]:
    """parent 辞書を goal から start まで辿り、start→goal 順のノード列に直す。"""
    path = [goal]
    while path[-1] != start:
        path.append(parent[path[-1]])
    path.reverse()
    return path
