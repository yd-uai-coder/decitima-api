"""トポロジカルソート(DFS ベース)── プリミティブ。registry には載らない。

有向非巡回グラフ(DAG)の頂点を「すべての辺 u→v で u が v より前」に並べる。
工程管理では「先行タスクを必ず前に」の実行順 ── Critical Pathの前進パスがこの順で走る。

- DFS の後行順(帰りがけ)を積んで最後に反転する。
  `dfs_preorder` は行きがけ順・単一始点、ここは全始点 + 帰りがけ。
- 閉路検出: 探索中の頂点を「灰」に、灰の頂点へ戻る辺(back edge)を見たら `CyclicGraphError`。
  DAG でなければトポロジカル順は存在しない。
- 近傍は id 昇順で辿る ── 同じ DAG なら常に同じ順を返す(決定論)。

Kahn 法(入次数 0 をキューで剥がす BFS)との対比は `Phase-8-1.md` §2。
計算量: 時間 O(V + E)、空間 O(V)。
"""

from __future__ import annotations

import heapq
from collections.abc import Iterable, Mapping

# node -> 後続 node 群。全 node が key に含まれる前提(successors_from_edges が保証)
type Successors = Mapping[str, Iterable[str]]


class CyclicGraphError(Exception):
    """依存グラフに閉路があり、トポロジカル順が存在しない。"""


# def topological_sort(successors: Successors) -> list[str]:
#     """DFS版(後行順の反転)
#     successors を、全辺 u→v で u が先になる順に並べて返す(DFS 後行順の反転)。

#     閉路があれば CyclicGraphError。近傍を id 昇順で辿るので同じ DAG は同じ順を返す。
#     """
#     # 0=未訪問 / 1=探索中(灰)/ 2=完了(黒)
#     color: dict[str, int] = {}
#     order: list[str] = []

#     def _visit(node: str) -> None:
#         color[node] = 1
#         for nxt in sorted(successors.get(node, ())):
#             state = color.get(nxt, 0) # nodeをキーにcolorの値を参照 -> 0で登録されているか、colorに存在しないなら0
#             if state == 1:  # 灰へ戻る辺 = back edge = 閉路
#                 raise CyclicGraphError(f"cycle detected via edge into {nxt!r}")
#             if state == 0: # 未訪問なら_visitを再帰呼び出し
#                 _visit(nxt)

#         # 再帰呼び出し分の完了順（後に呼びだされたものから先に処理する）
#         color[node] = 2
#         order.append(node)  # 帰りがけに積む

#     for node in sorted(successors):
        
#         if color.get(node, 0) == 0: 
#             _visit(node)
#     return order[::-1]  # 反転してトポロジカル順に


# def has_cycle(successors: Successors) -> bool:
#     """依存グラフに閉路があれば True。validation.py の hard ゲート用 ── 例外でなく bool。"""
#     try:
#         topological_sort(successors)
#     except CyclicGraphError:
#         return True
#     return False


def topological_sort(successors: Successors) -> list[str]:
    """Kahn法(入次数ベース、反復)
    successors を、全辺 u→v で u が先になる順に並べて返す(Kahn 法・入次数ベース)。

    入次数(そのノードへ入ってくる辺の数)が 0 のノードを優先度付きキュー(id昇順)に入れ、
    取り出すたびに後続の入次数を1減らし、0になったらキューへ足す反復を繰り返す。
    出力数が全ノード数に届かなければ、入次数が0にならないノードが残っている = 閉路。
    id昇順キューなので同じ DAG は常に同じ順(辞書順)を返す。
    """
    nodes = sorted(successors)
    # 入次数: 全 node を 0 で初期化してから辺を数える(孤立 node も 0 のまま残る)
    indegree: dict[str, int] = dict.fromkeys(nodes, 0)
    for node in nodes:
        for nxt in successors.get(node, ()):
            indegree[nxt] = indegree.get(nxt, 0) + 1

    # 入次数 0 のノードから開始。heapq で id昇順に取り出す(決定論・辞書順)
    queue: list[str] = [n for n in nodes if indegree[n] == 0]
    heapq.heapify(queue)

    order: list[str] = []
    while queue:
        node = heapq.heappop(queue)
        order.append(node)
        for nxt in sorted(successors.get(node, ())):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                heapq.heappush(queue, nxt)

    if len(order) != len(nodes):
        # 入次数が 0 に届かず出力されなかったノードが残っている = 閉路上(またはその先)
        stuck = sorted(set(nodes) - set(order))
        raise CyclicGraphError(f"cycle detected: indegree never reached 0 for {stuck!r}")
    return order


def has_cycle(successors: Successors) -> bool:
    """依存グラフに閉路があれば True。validation.py の hard ゲート用 ── 例外でなく bool。"""
    try:
        topological_sort(successors)
    except CyclicGraphError:
        return True
    return False


def successors_from_edges(
    nodes: Iterable[str], edges: Iterable[tuple[str, str]]
) -> dict[str, list[str]]:
    """(node 群, (from, to) 辺群)から successors 隣接リストを作る。

    孤立 node も後続だけの node も key に含める ── topological_sort / cpm が全 node を漏らさない。
    """
    adjacency: dict[str, list[str]] = {n: [] for n in nodes}
    for src, dst in edges:
        adjacency.setdefault(src, []).append(dst)
        adjacency.setdefault(dst, [])
    return adjacency
