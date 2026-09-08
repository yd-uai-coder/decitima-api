"""BruteForceRouteStrategy(全探索) ── start→goal の全単純パスを列挙して最小重みを選ぶ。

Phase 3 で追加。役割は 2 つ:
  1. 正解オラクル ── Dijkstra 等の手実装アルゴリズムが最適解を返しているかを、
     小規模グラフで裏取りする
  2. ベンチマークの 2 本目の対象 ── Dijkstra と時間・操作回数を並べると
     「賢いアルゴリズムがどれだけ効くか」「どのサイズで破綻するか」が数字で見える。

単純パス数は最悪で指数(O(V!) 相当)。**小さいグラフ専用**。
solve は純粋・検証しない(Phase-0-4.md §2.2)。制約充足の判定は Verification の仕事。
"""

from __future__ import annotations

from app.algorithms.graph.adjacency import build_adjacency
from app.domain.problems.problem import (
    ForbiddenConstraint,
    OptimizationProblem,
    RequiredInclusionConstraint,
)
from app.domain.problems.route_planner import RouteData
from app.domain.solutions.route_planner import RouteSolution
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution


class BruteForceRouteStrategy:
    """全単純パス列挙による route_planning の厳密解。学習・オラクル用。"""

    meta = AlgorithmMeta(
        name="brute_force",
        family="optimization",
        implementation="handwritten",
        time_complexity="O(V!)",
        space_complexity="O(V)",
    )

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data = problem.data
        # registry 経由なら必ず RouteData。念のため契約を確認する
        if not isinstance(data, RouteData):
            raise TypeError(f"BruteForceRouteStrategy expects RouteData, got {type(data).__name__}")

        # 制約から「禁止エッジ」「必須経由ノード」を集める
        forbidden: set[str] = set()
        required: list[str] = []
        for c in problem.constraints:
            if isinstance(c, ForbiddenConstraint):
                forbidden.update(c.items)
            elif isinstance(c, RequiredInclusionConstraint):
                required.extend(c.items)

        adjacency = build_adjacency(data, forbidden)
        required_set = set(required)

        best_nodes: list[str] | None = None
        best_edges: list[str] = []
        best_weight = float("inf")
        ops = 0  # metrics["_ops"] ── 展開した部分パスの数(= DFS スタックの pop 回数)

        # スタック要素: (現在ノード, ノード列, エッジ列, 訪問済み集合, 累積重み)
        stack: list[tuple[str, list[str], list[str], frozenset[str], float]] = [
            (data.start, [data.start], [], frozenset({data.start}), 0.0)
        ]
        while stack:
            node, nodes, edges, visited, weight = stack.pop()
            ops += 1
            # goal に着いたパス ── required を全部通っていれば候補にする
            if node == data.goal:
                if required_set <= set(nodes) and weight < best_weight:
                    best_weight = weight
                    best_nodes = list(nodes)
                    best_edges = list(edges)
                continue
            for nxt, edge_id, w in adjacency.get(node, ()):
                # 単純パスなので訪問済みノードには戻らない
                if nxt in visited:
                    continue
                stack.append((nxt, [*nodes, nxt], [*edges, edge_id], visited | {nxt}, weight + w))

        if best_nodes is None:
            # start→goal の(required を満たす)パスが 1 本も無い
            return CandidateSolution(
                status="infeasible",
                assignments=RouteSolution(path_node_ids=[], path_edge_ids=[], total_weight=0.0),
                metrics={"_ops": float(ops)},
                produced_by=self.meta,
            )
        return CandidateSolution(
            status="valid",  # 「hard 制約を満たすか」は Verification が後で判定する
            assignments=RouteSolution(
                path_node_ids=best_nodes, path_edge_ids=best_edges, total_weight=best_weight
            ),
            metrics={"total_weight": best_weight, "_ops": float(ops)},
            produced_by=self.meta,
        )
