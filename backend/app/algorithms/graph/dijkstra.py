"""DijkstraStrategy(ダイクストラ法) ── 優先度キューを用いた手実装のダイクストラ法。
  - 負の重みを扱えない
  - 負閉路を検出できない
   -> BellmanFordStrategy(ベルマン・フォード法)で解決する
"""

from __future__ import annotations

# ヒープ（heap：木構造）を扱う。主に 優先度付きキュー（Priority Queue） を実装するときに使用
import heapq

from app.domain.problems.problem import OptimizationProblem
from app.domain.problems.route_planner import RouteData
from app.algorithms.graph.adjacency import (
    Adjacency,
    build_adjacency,
    has_negative_weight,
)

from app.algorithms.graph.segments import (
    Segment,
    collect_route_constraints,
    negative_weight_violation,
    plan_route,
    route_solution,
    reconstruct_path,
)

from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution


def _dijkstra_segment(adjacency: Adjacency, start: str, goal: str) -> tuple[Segment | None, int]:
    """start→goal の最短経路を1区間ぶん求める。到達不能なら (None, pops)。
    
    pops は「優先度キューから取り出した回数」= 操作回数の目安(metrics["_ops"])。
    """
    
    dist: dict[str, float] = {start: 0.0} # dist[n] = start から n までの暫定最短距離
    prev: dict[str, tuple[str, str]] = {} # prev[n] = 最短経路木で n の1つ前の (ノード id, エッジ id)
    heap: list[tuple[float, str]] = [(0.0, start)]  # ヒープ要素: (暫定距離, ノード id)
    settled: set[str] = set() # 訪問済ノードのset
    pops = 0

    while heap:
        # ヒープから最小要素の取り出し
        d, node = heapq.heappop(heap)
        pops += 1
        # 同じノードが古い距離で複数回入っていることがあるのでスキップ
        if node in settled:
            continue
        settled.add(node)
        if node == goal:
            break
        for nxt, edge_id, weight in adjacency.get(node, ()):
            nd = d + weight
            # より短い経路が見つかったら更新してヒープに積む
            if nd < dist.get(nxt, float("inf")):
                dist[nxt] = nd
                prev[nxt] = (node, edge_id)
                heapq.heappush(heap, (nd, nxt))

    if goal not in settled:
        return None, pops
    # prev を goal から辿って start→goal 順のノード列・エッジ列に直す。
    return reconstruct_path(prev, start, goal, dist[goal]), pops


class DijkstraStrategy:
    """手実装のダイクストラ法。学習・再現性の説明用(implementation="handwritten")。"""

    meta = AlgorithmMeta(
        name="dijkstra",
        family="graph",
        implementation="handwritten",
        time_complexity="O((V+E) log V)",
        space_complexity="O(V)",
    )

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        """route_planning の OptimizationProblem を解いて候補解を返す。"""
        data = problem.data
        # registry 経由なら必ず RouteData。念のため契約を確認する
        if not isinstance(data, RouteData):
            raise TypeError(f"DijkstraStrategy expects RouteData, got {type(data).__name__}")

        # 制約から「禁止エッジ」「必須経由ノード」を集める
        forbidden, required = collect_route_constraints(problem)
        adjacency = build_adjacency(data, forbidden)

        # 負辺があると Dijkstra の settled 不変条件が壊れる ── 負辺は Bellman-Ford の担当
        # この時点でエラーを返すのではなく、制約違反という状態を返す。※プログラムを停めない。
        if has_negative_weight(adjacency):
            return route_solution(
                None, 0, self.meta, violations=[negative_weight_violation("dijkstra")]
            )

        seg, ops = plan_route(
            data.start,
            data.goal,
            required,
            lambda a, b: _dijkstra_segment(adjacency, a, b),
        )
        return route_solution(seg, ops, self.meta)


