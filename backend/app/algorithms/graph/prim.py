"""PrimStrategy(プリム法)── 木を1ノードずつ育て、木の外へ出る最小重みリンクを取り続ける MST。

Kruskal が「辺を軽い順に見る」のに対し、Prim は「今の木から出る辺のうち最小」を優先度キューで選ぶ。
`_ops` = ヒープから取り出した回数。
"""

from __future__ import annotations

import heapq

from app.algorithms.graph.adjacency import build_link_adjacency
from app.algorithms.graph.mst import (
    mst_solution,
    parse_network_problem,
    resolve_required,
)
from app.domain.problems.problem import OptimizationProblem
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution


class PrimStrategy:
    """手実装のプリム法(implementation="handwritten")。"""

    meta = AlgorithmMeta(
        name="prim",
        family="graph",
        implementation="handwritten",
        time_complexity="O(E log V)",
        space_complexity="O(V)",
    )

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data, forbidden, required = parse_network_problem(problem)
        if not data.nodes:
            return mst_solution([], 0, self.meta)

        resolved = resolve_required(data, forbidden, required)
        if resolved is None:
            return mst_solution(None, 0, self.meta)
        selected, _uf = resolved

        adjacency = build_link_adjacency(data, forbidden)
        link_by_id = {link.id: link for link in data.links}
        # 木に入っているノード: 必須リンクの端点 + 最初のノード
        in_tree: set[str] = {ep for link in selected for ep in link.endpoints}
        in_tree.add(data.nodes[0].id)

        # heap 要素: (weight, link_id, 到達先ノード)
        heap: list[tuple[float, str, str]] = []
        for node in in_tree:
            for nxt, lid, w in adjacency.get(node, ()):
                if nxt not in in_tree:
                    heapq.heappush(heap, (w, lid, nxt))

        need = max(len(data.nodes) - 1, 0)
        ops = 0
        while heap and len(selected) < need:
            w, lid, v = heapq.heappop(heap)
            ops += 1
            if v in in_tree:
                continue  # 別ルートで先に木へ入った
            in_tree.add(v)
            selected.append(link_by_id[lid])
            for nxt, nlid, nw in adjacency.get(v, ()):
                if nxt not in in_tree:
                    heapq.heappush(heap, (nw, nlid, nxt))

        if len(selected) != need or len(in_tree) != len(data.nodes):
            return mst_solution(None, ops, self.meta)
        return mst_solution(selected, ops, self.meta)
