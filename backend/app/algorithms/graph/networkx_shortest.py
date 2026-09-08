"""NetworkxShortestPath ── networkx の最短経路を AlgorithmStrategy で包む(産業ソルバートラック)。

手実装 Dijkstra と同じ `meta.name="dijkstra"` にし、`implementation="library:networkx"` で
区別する狙い:
  - ベンチマークで「同じアルゴリズムの 手実装 vs ライブラリ」を並べる(Phase 14 の土台)
  - 手実装 Dijkstra / Bellman-Ford の**別実装オラクル**(BruteForce は厳密最適、これは別実装照合)

`_ops` は積まない ── 仕事の大半が C 実装の中で外から数えられない。「ライブラリトラックは
操作回数を出せない」= 2 トラック比較の論点そのもの
"""

from __future__ import annotations

from itertools import pairwise

import networkx as nx

from app.algorithms.graph.segments import (
    Segment,
    collect_route_constraints,
    route_solution,
)
from app.algorithms.graph.waypoints import optimize_waypoint_order
from app.algorithms.graph.segments import negative_cycle_violation
from app.domain.problems.problem import OptimizationProblem
from app.domain.problems.route_planner import RouteData
from app.domain.solutions.solution import (
    AlgorithmMeta,
    CandidateSolution,
)


def _add_min_edge(graph: nx.Graph, u: str, v: str, edge_id: str, weight: float) -> None:
    """u-v に既にエッジがあれば軽い方だけ残す(RouteData は平行エッジを持てるが nx.Graph は不可)。"""
    if graph.has_edge(u, v) and graph[u][v]["weight"] <= weight:
        return
    graph.add_edge(u, v, id=edge_id, weight=weight)


def _to_graph(data: RouteData, forbidden: set[str]) -> nx.Graph:
    """RouteData → networkx グラフ。有向エッジが1本でもあれば DiGraph。"""
    directed = any(e.directed for e in data.edges)
    graph: nx.Graph = nx.DiGraph() if directed else nx.Graph()
    graph.add_nodes_from(n.id for n in data.nodes)
    for e in data.edges:
        if e.id in forbidden:
            continue
        _add_min_edge(graph, e.source, e.target, e.id, e.weight)
        if not e.directed:
            _add_min_edge(graph, e.target, e.source, e.id, e.weight)
    return graph


class NetworkxShortestPath:
    """networkx の shortest_path / bellman_ford_path ラッパー。"""

    meta = AlgorithmMeta(
        name="dijkstra_nx",
        family="graph",
        implementation="library:networkx",
        time_complexity="O((V+E) log V)",
        space_complexity="O(V+E)",
    )

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data = problem.data
        # registry 経由なら必ず RouteData。念のため契約を確認する
        if not isinstance(data, RouteData):
            raise TypeError(f"NetworkxShortestPath expects RouteData, got {type(data).__name__}")

        # 制約から「禁止エッジ」「必須経由ノード」を集める
        forbidden, required = collect_route_constraints(problem)

        
        graph = _to_graph(data, forbidden)
        negative = any(w < 0 for *_e, w in graph.edges(data="weight"))

        def cost(a: str, b: str) -> float | None:
            try:
                if negative:
                    return nx.bellman_ford_path_length(graph, a, b)
                return nx.dijkstra_path_length(graph, a, b)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                return None
            except nx.NetworkXUnbounded:
                return None  # 負閉路 ── 下で infeasible にする

        # 負閉路チェック(start から届く範囲)
        if negative:
            try:
                nx.bellman_ford_predecessor_and_distance(graph, data.start)
            except nx.NetworkXUnbounded:
                return route_solution(
                    None, None, self.meta, violations=[negative_cycle_violation()]
                )

        order = optimize_waypoint_order(data.start, data.goal, required, cost)
        if order is None:
            return route_solution(None, None, self.meta)

        node_ids: list[str] = []
        edge_ids: list[str] = []
        total = 0.0
        for u, v in pairwise(order):
            try:
                path = (
                    nx.bellman_ford_path(graph, u, v) if negative else nx.dijkstra_path(graph, u, v)
                )
            except (nx.NetworkXNoPath, nx.NodeNotFound, nx.NetworkXUnbounded):
                return route_solution(None, None, self.meta)
            seg_edges = [graph[path[i]][path[i + 1]]["id"] for i in range(len(path) - 1)]
            seg_weight = sum(graph[path[i]][path[i + 1]]["weight"] for i in range(len(path) - 1))
            node_ids.extend(path if not node_ids else path[1:])
            edge_ids.extend(seg_edges)
            total += seg_weight

        return route_solution(Segment(node_ids, edge_ids, total), None, self.meta)