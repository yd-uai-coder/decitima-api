"""グラフの隣接表現(プリミティブ)。

- `build_adjacency` … RouteData(有向/無向混在)→ 重み付き隣接リスト
- `build_link_adjacency` … NetworkDesignData(常に無向)→ 重み付き隣接リスト
- `build_leg_adjacency` … TravelData(常に無向)→ 移動 cost の隣接リスト
- `build_logistics_adjacency` … LogisticsData(有向/無向混在)→ 重み付き隣接リスト
- `has_negative_weight` … 負辺が1本でもあるか(Dijkstra / A* の前提チェック)
- `plain_adjacency` … 重み付き隣接 → id だけの素の隣接(BFS / 連結性判定が使う)
"""

from __future__ import annotations

from collections.abc import Iterable

from app.domain.problems.logistics import LogisticsData
from app.domain.problems.network_design import NetworkDesignData
from app.domain.problems.route_planner import RouteData
from app.domain.problems.travel_planner import TravelData

# 隣接リストの1エントリ: (隣接ノード id, そのエッジの id, 重み)
type Adjacency = dict[str, list[tuple[str, str, float]]]


def build_adjacency(data: RouteData, forbidden_edge_ids: set[str]) -> Adjacency:
    """RouteData から重み付き隣接リストを作る。forbidden のエッジは張らない。"""
    adjacency: Adjacency = {node.id: [] for node in data.nodes}
    for edge in data.edges:
        if edge.id in forbidden_edge_ids: # エッジ内に禁止区間が含まれる場合はスキップ
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

def build_leg_adjacency(data: TravelData, forbidden_leg_ids: set[str]) -> Adjacency:
    """TravelData から移動 cost の重み付き隣接リストを作る。leg は常に無向。

    weight は `travel_cost`(費用)。時間で見たい呼び出し側は自分で作り直す。
    Floyd-Warshall(`floyd_warshall.py`)がこれを受けて全点対距離を出す。
    """
    adjacency: Adjacency = {place.id: [] for place in data.places}
    for leg in data.legs:
        if leg.id in forbidden_leg_ids:
            continue
        a, b = leg.endpoints
        adjacency.setdefault(a, []).append((b, leg.id, leg.travel_cost))
        adjacency.setdefault(b, []).append((a, leg.id, leg.travel_cost))
    return adjacency


def build_logistics_adjacency(data: LogisticsData, forbidden_segment_ids: set[str]) -> Adjacency:
    """LogisticsData から重み付き隣接リストを作る。`build_adjacency`(RouteData)と同型 ──

    `segment.directed` が False の区間は逆向きも張る(無向扱い)。Floyd-Warshall(7-1)が
    これを受けてデポ・配送先間の全点対距離を出す(`logistics_common.all_pairs`、9-2)。
    """
    adjacency: Adjacency = {node.id: [] for node in data.nodes}
    for seg in data.segments:
        if seg.id in forbidden_segment_ids:
            continue
        adjacency.setdefault(seg.source, []).append((seg.target, seg.id, seg.distance))
        if not seg.directed:
            adjacency.setdefault(seg.target, []).append((seg.source, seg.id, seg.distance))
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
