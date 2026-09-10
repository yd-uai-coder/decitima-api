"""problem_type からアルゴリズム候補を引く仕組み。"""
from __future__ import annotations

from app.algorithms.base import AlgorithmStrategy
from app.domain.problems.problem import OptimizationProblem
from app.algorithms.graph.dijkstra import DijkstraStrategy
from app.algorithms.optimization.brute_force import BruteForceRouteStrategy
from app.algorithms.optimization.knapsack import KnapsackDpTravelStrategy
from app.algorithms.optimization.greedy_travel import GreedyTravelStrategy
from app.algorithms.optimization.brute_force_travel import BruteForceTravelStrategy
from app.algorithms.graph.bellman_ford import BellmanFordStrategy
from app.algorithms.graph.a_star import AStarStrategy
from app.algorithms.graph.networkx_shortest import NetworkxShortestPath   # ← この章で有効化
from app.algorithms.graph.kruskal import KruskalStrategy
from app.algorithms.graph.prim import PrimStrategy
from app.algorithms.graph.networkx_mst import NetworkxMST
from app.algorithms.scheduling.greedy import GreedyShiftStrategy
from app.algorithms.scheduling.backtracking import BacktrackingShiftStrategy   # ← 有効化
from app.algorithms.scheduling.branch_and_bound import BranchAndBoundShiftStrategy
from app.algorithms.scheduling.ortools_cpsat import OrToolsCpSatShiftStrategy


REGISTRY: dict[str, list[AlgorithmStrategy]] = {
    # 新アルゴリズムの追加はリストに 1 行。既存コードに触れない(オープン・クローズドの原則)。
    # **手実装 strategy を先頭に置く** 
    # find_strategy の requested 一致は next(...) で先頭を返す。
    # ?algorithm=dijkstra` は手実装が当たる(望ましい既定)。
    "route_planning": [
        DijkstraStrategy(),
        BellmanFordStrategy(), 
        AStarStrategy(),
        NetworkxShortestPath(), # 手実装 Dijkstra と同 name / 別 implementation
        BruteForceRouteStrategy(), 
    ],
    "shift_scheduling": [
        GreedyShiftStrategy(),
        BacktrackingShiftStrategy(),
        BranchAndBoundShiftStrategy(),
        OrToolsCpSatShiftStrategy(),
    ],
    "network_design": [
        KruskalStrategy(),
        PrimStrategy(),
        NetworkxMST(),
    ],
    "travel_planning": [ 
        KnapsackDpTravelStrategy(),
        GreedyTravelStrategy(),
        BruteForceTravelStrategy(),
],
}


def get_strategies(problem_type: str) -> list[AlgorithmStrategy]:
    """problem_type に対応するアルゴリズム候補を返す。未登録なら空リスト。"""
    return REGISTRY.get(problem_type, [])

#OptimizationProblemを受け取り、上記のget_strategiesに渡す
def find_strategy(
    problem: OptimizationProblem, requested: str | None = None
) -> AlgorithmStrategy | None:
    """該当が無ければ None を返す(送出はしない)。
    - requested 指定があれば meta.name 一致を最優先
    """
    candidates = get_strategies(problem.problem_type)
    if not candidates:
        return None
    if requested is not None:
        return next((s for s in candidates if s.meta.name == requested), None)
    return candidates[0]


def all_strategies() -> list[tuple[str, AlgorithmStrategy]]:
    """(problem_type, strategy) の全ペア。GET /api/v1/algorithms が使う。"""
    return [(pt, s) for pt, strategies in REGISTRY.items() for s in strategies]
