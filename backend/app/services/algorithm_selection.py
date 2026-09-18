"""アルゴリズム選択(サービス層)。"""

import math

from app.algorithms.base import AlgorithmStrategy
from app.algorithms.registry import find_strategy, get_strategies
from app.domain.problems.problem import OptimizationProblem
from app.domain.problems.project_manager import ProjectData
from app.domain.problems.route_planner import RouteData
from app.domain.problems.shift_scheduler import ShiftData
from app.domain.problems.travel_planner import TravelData
from app.services.errors import NoAlgorithmError

# knapsack_dp は O(places数 × floor(budget) × floor(time_budget)) の擬多項式。
# 実測(cap_a=15000,cap_b=16,n=5→0.74秒 / cap_a=100000,cap_b=16,n=5→5.23秒)から、
# /benchmark の runs=3 逐次実行でも SOLVE_TIMEOUT_SECONDS(10秒)に収まる規模に制限する。
# 超える場合は解の質を多少落としてでも確実に完走する greedy にフォールバックする。
# (暫定閾値。Phase 15 の性能テストで見直す可能性あり)
_MAX_KNAPSACK_DP_CELLS = 4_000_000

def _preferred_name(problem: OptimizationProblem) -> str | None:
    """問題特性から使いたい meta.name を決める。候補に無ければ呼び出し側が先頭にフォールバック。"""
    data = problem.data
    if isinstance(data, RouteData):
        # 負辺 → Bellman-Ford(Dijkstra / A* は settled 不変条件が壊れる)
        if data.allow_negative or any(e.weight < 0 for e in data.edges):
            return "bellman_ford"
        # 全ノードに座標がある → A*(ヒューリスティックが効く)
        if data.nodes and all(n.x is not None and n.y is not None for n in data.nodes):
            return "a_star"
        # 既定は手実装 Dijkstra(library:networkx は明示 request 時のみ)
        return "dijkstra"
    if problem.problem_type == "network_design":
        return "kruskal"
    if isinstance(data, ShiftData):
        # 既定は Backtracking(小規模で最適)。実規模は ?algorithm=cp_sat を明示 request
        return "backtracking"
    if problem.problem_type == "travel_planning" and isinstance(data, TravelData):
        # 既定は Knapsack DP。ただし budget/time_budget が大きく DP グリッドが
        # 肥大化する場合はタイムアウト連鎖(裏スレッドは止まらない)を避けるため greedy に
        # フォールバックする。厳密な確認は ?algorithm=knapsack_dp / brute_force を明示 request
        cells = len(data.places) * math.floor(data.budget) * math.floor(data.time_budget)
        if cells > _MAX_KNAPSACK_DP_CELLS:
            return "greedy"
        return "knapsack_dp"
    if isinstance(data, ProjectData):
        # 資源制約あり → priority_list(資源 feasible な貪欲)。厳密は ?algorithm=cp_sat
        # 資源制約なし → cpm(純粋なクリティカルパス。O(V+E))
        return "priority_list" if data.resource_capacity is not None else "cpm"
    if problem.problem_type == "logistics_planning":  # (Phase 9-7)
        # 既定は Knapsack DP(高速)。厳密確認は ?algorithm=brute_force、
        # 台数最小化は ?algorithm=pulp_milp を明示 request
        return "knapsack_dp"
    return None


# 責務の分離
# registry.find_strategyは検索結果を返すのみ。
# エラーハンドリングについてはserviceで担当する。(例外のスローまで)
# 例外処理の内容は別のファイルにまとめる
def select_strategy(
    problem: OptimizationProblem, requested: str | None = None
) -> AlgorithmStrategy:
    """problem に適用するアルゴリズムを1つ選ぶ。無ければ NoAlgorithmError。"""
    if requested is not None:
        strategy = find_strategy(problem, requested)
        if strategy is None:
            raise NoAlgorithmError(
                f"algorithm {requested!r} is not registered for {problem.problem_type!r}"
            )
        return strategy

    candidates = get_strategies(problem.problem_type)
    if not candidates:
        raise NoAlgorithmError(f"no algorithm registered for {problem.problem_type!r}")

    preferred = _preferred_name(problem)
    return next((s for s in candidates if s.meta.name == preferred), candidates[0])
