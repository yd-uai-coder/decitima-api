"""NetworkxMST ── networkx の minimum_spanning_tree を AlgorithmStrategy で包む。

手実装 Kruskal と同じ `meta.name="kruskal"`、`implementation="library:networkx"`。
Kruskal / Prim の別実装オラクル + 2 トラック比較。`_ops` は積まない。

必須リンクは networkx に直接の仕組みが無いので、重みを一時的に最小以下に下げて
「必ず選ばれる」ようにしてから MST を取り、id で元のリンクに戻す。
"""

from __future__ import annotations

import networkx as nx

from app.algorithms.graph.mst import mst_solution, parse_network_problem
from app.domain.problems.problem import OptimizationProblem
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution


class NetworkxMST:
    """networkx の minimum_spanning_tree ラッパー。"""

    meta = AlgorithmMeta(
        name="kruskal_nx",
        family="graph",
        implementation="library:networkx",
        time_complexity="O(E log E)",
        space_complexity="O(V+E)",
    )

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data, forbidden, required = parse_network_problem(problem)
        link_by_id = {link.id: link for link in data.links}
        need = max(len(data.nodes) - 1, 0)

        # 必須リンクを強制するための「下駄」(全 weight より十分小さい値)
        base = min((link.weight for link in data.links), default=0.0)
        forced_bias = base - 1.0 - len(data.links)

        graph = nx.Graph()
        graph.add_nodes_from(node.id for node in data.nodes)
        for link in data.links:
            if link.id in forbidden:
                continue
            a, b = link.endpoints
            weight = forced_bias if link.id in required else link.weight
            # Graph は平行辺を持てないので、軽い方だけ残す
            if graph.has_edge(a, b) and graph[a][b]["weight"] <= weight:
                continue
            graph.add_edge(a, b, id=link.id, weight=weight)

        tree = nx.minimum_spanning_tree(graph, weight="weight")
        selected_ids = [d["id"] for _u, _v, d in tree.edges(data=True)]

        # 必須リンクが候補に無い / 使えない指定と矛盾 → 全部は選べない
        if any(link_by_id.get(lid) is None or lid in forbidden for lid in required):
            return mst_solution(None, None, self.meta)
        if len(selected_ids) != need or not all(lid in selected_ids for lid in required):
            return mst_solution(None, None, self.meta)  # 非連結 or 必須を取りこぼした

        return mst_solution([link_by_id[lid] for lid in selected_ids], None, self.meta)
