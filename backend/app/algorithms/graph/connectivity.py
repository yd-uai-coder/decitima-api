"""グラフの連結性クエリ(プリミティブ)。

`network_design` の「全拠点が連結か」= 敷設可能リンク全体で 1 つに繋がっているか、の判定。
route の `route_reachable` と同じ「BFS を走らせる計算」なので、`domain` ではなく `algorithms` に
置き、判定(hard ゲート)は `services/validation.py` が行う。
registry には載せない。
"""

from __future__ import annotations

from collections.abc import Iterable

from app.algorithms.graph.adjacency import Adjacency, plain_adjacency
from app.algorithms.search.bfs import reachable_nodes


def all_nodes_connected(node_ids: Iterable[str], adjacency: Adjacency) -> bool:
    """adjacency のグラフ上で node_ids 全部が 1 つの連結成分に入っていれば True。

    ノード 0〜1 個は True(全域木の辺数は max(V-1, 0))。
    Validation が「敷設可能リンク全体で全拠点が繋がるか」の hard ゲートに使う。
    """
    ids = list(node_ids)
    if len(ids) <= 1:
        return True
    reached = reachable_nodes(plain_adjacency(adjacency), ids[0])
    return all(nid in reached for nid in ids)


def forms_spanning_tree(node_ids: Iterable[str], link_pairs: Iterable[tuple[str, str]]) -> bool:
    """link_pairs が node_ids 全体を繋ぐ全域木か。

    「辺数 == V-1」かつ「連結」なら閉路は無い(木の性質)。Verification が
    NetworkDesignSolution の「選んだリンクが本当に全域木か」を判定するのに使う。
    """
    ids = list(node_ids)
    pairs = list(link_pairs)
    if len(pairs) != max(len(ids) - 1, 0):
        return False
    if len(ids) <= 1:
        return True
    adj: dict[str, list[str]] = {i: [] for i in ids}
    for a, b in pairs:
        adj.setdefault(a, []).append(b)
        adj.setdefault(b, []).append(a)
    reached = reachable_nodes(adj, ids[0])
    return all(nid in reached for nid in ids)
