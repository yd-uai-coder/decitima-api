"""グラフの到達可能性クエリ(プリミティブ)。

`build_adjacency`(dijkstra.py)と BFS(search/bfs.py)の薄い合成。「禁止エッジを除いた
グラフで goal が start から到達できるか」を bool で返すだけの純粋関数。
Validation の実行可能性チェック(ProblemValidationService)が hard ゲートとして使う。
registry には載せない ── ストラテジーではなくグラフのクエリ。

"""

from __future__ import annotations

from app.algorithms.graph.adjacency import build_adjacency, plain_adjacency, build_logistics_adjacency
from app.algorithms.search.bfs import reachable_nodes
from app.domain.problems.route_planner import RouteData
from app.domain.problems.logistics import LogisticsData

def route_reachable(data: RouteData, forbidden_edge_ids: set[str]) -> bool:
    """禁止エッジを除いたグラフで data.goal が data.start から到達可能なら True。"""

    # DijkstraStrategy：ダイクストラ法
    # RouteData から重み付き隣接リスト(_Adjacency)を作る 
    adjacency = build_adjacency(data, forbidden_edge_ids)
    return data.goal in reachable_nodes(plain_adjacency(adjacency), data.start)


def logistics_deliveries_reachable(data: LogisticsData, forbidden_segment_ids: set[str]) -> bool:
    """禁止区間を除いた道路網で、デポから全配送先ノードへ到達可能なら True(複数ターゲット版)。"""
    adjacency = build_logistics_adjacency(data, forbidden_segment_ids)
    reached = reachable_nodes(plain_adjacency(adjacency), data.depot_id)
    return all(d.node_id in reached for d in data.deliveries)
