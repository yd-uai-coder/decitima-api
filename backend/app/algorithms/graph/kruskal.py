"""KruskalStrategy(クラスカル法)── リンクを軽い順に見て、閉路を作らないものだけ採用する MST。

Union-Find で「この2拠点はもう繋がっているか(= この辺は閉路になるか)」を O(1) 判定する。
`union_find.py`(プリミティブ)を `KruskalStrategy.solve`(ストラテジー)が使う典型例

`_ops` = union を試みた回数。
"""

from __future__ import annotations

from app.algorithms.graph.mst import (
    mst_solution,
    parse_network_problem,
    resolve_required,
)
from app.domain.problems.problem import OptimizationProblem
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution


class KruskalStrategy:
    """手実装のクラスカル法(implementation="handwritten")。"""

    meta = AlgorithmMeta(
        name="kruskal",
        family="graph",
        implementation="handwritten",
        time_complexity="O(E log E)",
        space_complexity="O(V)",
    )

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data, forbidden, required = parse_network_problem(problem)

        resolved = resolve_required(data, forbidden, required)
        if resolved is None:
            return mst_solution(None, 0, self.meta)  # 必須リンクが矛盾
        selected, uf = resolved
        ops = 0

        need = max(len(data.nodes) - 1, 0)
        # 残りの候補を weight 昇順に見て、閉路にならないものを採る
        rest = sorted(
            (link for link in data.links if link.id not in forbidden and link.id not in required),
            key=lambda link: link.weight,
        )
        for link in rest:
            if len(selected) == need:
                break
            a, b = link.endpoints
            ops += 1
            if uf.union(a, b):  # False なら a,b は既に連結 → この辺は閉路
                selected.append(link)

        if len(selected) != need:
            return mst_solution(None, ops, self.meta)  # 全拠点を繋げなかった
        return mst_solution(selected, ops, self.meta)
