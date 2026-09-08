"""グラフの隣接表現(プリミティブ)。

- `build_adjacency` … RouteData(有向/無向混在)→ 重み付き隣接リスト
- `build_link_adjacency` … NetworkDesignData(常に無向)→ 重み付き隣接リスト(5-3)
- `plain_adjacency` … 重み付き隣接 → id だけの素の隣接(BFS / 連結性判定が使う)
- `has_negative_weight` … 負辺が1本でもあるか(Dijkstra / A* の前提チェック)

CSR 行列ビルダー(`to_csr`)は入れない ── scipy を足す Phase まで遅延
(`textbook/appendix/library-fork-impact.md` フック①)。
Phase 5-3 で `network_design` 用の `build_link_adjacency` をこのファイルに足す
(link 専用の無向隣接。route 消費者がいないので Phase 5 まで遅延)。
"""

from __future__ import annotations

from collections.abc import Iterable

from app.domain.problems.network_design import NetworkDesignData
from app.domain.problems.route_planner import RouteData

# 隣接リストの1エントリ: (隣接ノード id, そのエッジの id, 重み)
type Adjacency = dict[str, list[tuple[str, str, float]]]


def build_adjacency(data: RouteData, forbidden_edge_ids: set[str]) -> Adjacency:
    """RouteData から重み付き隣接リストを作る。forbidden のエッジは張らない。"""
    adjacency: Adjacency = {node.id: [] for node in data.nodes}
    for edge in data.edges:
        if edge.id in forbidden_edge_ids:
            continue
        adjacency.setdefault(edge.source, []).append((edge.target, edge.id, edge.weight))
        if not edge.directed:
            # `edge.directed` が False のエッジは逆向きも張る(無向扱い)。
            adjacency.setdefault(edge.target, []).append((edge.source, edge.id, edge.weight))
    return adjacency


def build_link_adjacency(data: NetworkDesignData, forbidden_link_ids: set[str]) -> Adjacency:
    """NetworkDesignData から重み付き隣接リストを作る。リンクは常に無向。"""
    adjacency: Adjacency = {node.id: [] for node in data.nodes}
    for link in data.links:
        if link.id in forbidden_link_ids:
            continue
        a, b = link.endpoints
        adjacency.setdefault(a, []).append((b, link.id, link.weight))
        adjacency.setdefault(b, []).append((a, link.id, link.weight))
    return adjacency


def plain_adjacency(adjacency: Adjacency) -> dict[str, list[str]]:
    """重み付き隣接(nxt, edge_id, weight)から weight/edge_id を落として素の隣接にする。"""
    return {node: [nxt for nxt, _edge_id, _weight in edges] for node, edges in adjacency.items()}


def has_negative_weight(adjacency: Adjacency) -> bool:
    """隣接リストに負の重みが1本でもあれば True(Dijkstra / A* の前提が崩れる)。"""
    return any(weight < 0 for edges in adjacency.values() for _nxt, _id, weight in edges)


def node_ids(adjacency: Adjacency) -> Iterable[str]:
    """隣接リストが知っている全ノード id。"""
    return adjacency.keys()
