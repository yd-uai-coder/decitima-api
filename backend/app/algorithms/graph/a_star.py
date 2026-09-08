"""AStarStrategy(A* 探索)── ダイクストラに「goal への推定残距離 h(n)」を足して方向づける。

heap のキーを g(n)(start からの実距離)ではなく f(n) = g(n) + h(n) にするだけ。
h(n) が **可容**(実際の残距離を超えない)なら最適性は保たれ、h(n) が良いほど
探索するノードが減る(`_ops` が下がる)。

"""

from __future__ import annotations

import heapq
import math

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
    reconstruct_path,
    route_solution,
)
from app.domain.problems.problem import OptimizationProblem
from app.domain.problems.route_planner import RouteData
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution

# ノード id -> (x, y)。座標を持つノードだけ
type _Coords = dict[str, tuple[float, float]]


def _heuristic(coords: _Coords, node: str, goal: str) -> float:
    """node から goal への直線距離。どちらかに座標が無ければ 0(= 可容)。"""
    if node not in coords or goal not in coords:
        return 0.0
    (x1, y1), (x2, y2) = coords[node], coords[goal]
    return math.hypot(x1 - x2, y1 - y2)


def _astar_segment(
    adjacency: Adjacency, start: str, goal: str, coords: _Coords
) -> tuple[Segment | None, int]:
    """start→goal の最短経路を1区間ぶん。pops = heap から取り出した回数(metrics["_ops"])。"""

    g: dict[str, float] = {start: 0.0}  # start からの実距離
    prev: dict[str, tuple[str, str]] = {} # prev[n] = 最短経路木で n の1つ前の (ノード id, エッジ id)
    heap: list[tuple[float, str]] = [(_heuristic(coords, start, goal), start)] # ヒープ要素: (_heuristic, ノード id)
    settled: set[str] = set() # 訪問済ノードのset
    pops = 0

    while heap:
        # ヒープから最小要素の取り出し
        _f, node = heapq.heappop(heap)
        pops += 1
        # 同じノードが古い距離で複数回入っていることがあるのでスキップ
        if node in settled:
            continue
        settled.add(node)
        if node == goal:
            break
        for nxt, edge_id, weight in adjacency.get(node, ()):
            ng = g[node] + weight
            # より短い経路が見つかったら更新してヒープに積む
            if ng < g.get(nxt, float("inf")):
                g[nxt] = ng
                prev[nxt] = (node, edge_id)
                heapq.heappush(heap, (ng + _heuristic(coords, nxt, goal), nxt))

    if goal not in settled:
        return None, pops
    # 経路復元は Dijkstra / Bellman-Ford と共通 ── segments.reconstruct_path
    # prev を goal から辿って start→goal 順のノード列・エッジ列に直す。
    return reconstruct_path(prev, start, goal, g[goal]), pops


class AStarStrategy:
    """手実装の A* 探索(implementation="handwritten")。"""

    meta = AlgorithmMeta(
        name="a_star",
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
            raise TypeError(f"AStarStrategy expects RouteData, got {type(data).__name__}")
        
        # 制約から「禁止エッジ」「必須経由ノード」を集める
        forbidden, required = collect_route_constraints(problem)
        adjacency = build_adjacency(data, forbidden)
        if has_negative_weight(adjacency):
            return route_solution(
                None, 0, self.meta, violations=[negative_weight_violation("a_star")]
            )

        coords: _Coords = {
            n.id: (n.x, n.y) for n in data.nodes if n.x is not None and n.y is not None
        }
        seg, ops = plan_route(
            data.start,
            data.goal,
            required,
            lambda a, b: _astar_segment(adjacency, a, b, coords),
        )
        return route_solution(seg, ops, self.meta)
