"""BruteForceTravelStrategy。

place の部分集合を全列挙する厳密解(小規模専用の正解オラクル)。
`brute_force.py`(route の全単純パス列挙)/ `test_shift_breakdown.py::_brute_force_optimal` と同じ役割
── 「Knapsack DP / Greedy が小規模で最適を出せているか」を裏取りする。移動費用も込みで評価する
(DP の「移動を無視した上界」とは違い、これは真の最適)。

計算量: O(2^n) 個の部分集合 × 各部分集合の巡回順最適化。n ≤ 12 くらいまで。
`_ops` = 評価した部分集合の数。
"""

from __future__ import annotations

from itertools import combinations

from app.algorithms.optimization.travel_common import (
    all_pairs,
    order_and_cost,
    parse_travel_problem,
    place_utility,
    travel_solution,
)
from app.domain.problems.problem import OptimizationProblem
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution


class BruteForceTravelStrategy:
    """全部分集合を試して予算・時間内で効用最大の place 集合を選ぶ(オラクル)。"""

    meta = AlgorithmMeta(
        name="brute_force",
        family="optimization",
        implementation="handwritten",
        time_complexity="O(2^n * n!)",  # 部分集合 × 巡回順
        space_complexity="O(n)",
    )

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data, forbidden, required = parse_travel_problem(problem)
        cost_dist, time_dist = all_pairs(data)

        candidates = [p.id for p in data.places if p.id not in forbidden]
        req = [rid for rid in required if rid in candidates]
        free = [pid for pid in candidates if pid not in req]

        best_ids: list[str] = list(req)
        best_value = _plan_value(data, req, cost_dist, time_dist)
        ops = 0
        for k in range(len(free) + 1):
            for combo in combinations(free, k):
                ops += 1
                ids = [*req, *combo]
                plan = order_and_cost(data, ids, cost_dist, time_dist)
                if plan is None:
                    continue
                visit, cost, time = plan
                if cost > data.budget or time > data.time_budget:
                    continue
                value = sum(place_utility(data, p) for p in visit)
                if value > best_value:
                    best_value, best_ids = value, ids

        return travel_solution(data, best_ids, cost_dist, time_dist, ops, self.meta)


def _plan_value(data, ids, cost_dist, time_dist) -> float:  # noqa: ANN001
    plan = order_and_cost(data, ids, cost_dist, time_dist)
    if plan is None:
        return float("-inf")
    visit, cost, time = plan
    if cost > data.budget or time > data.time_budget:
        return float("-inf")
    return sum(place_utility(data, p) for p in visit)
