"""BruteForceLogisticsStrategy。

配送先→車両の全割当を列挙する厳密解(小規模専用の正解オラクル)。`brute_force_travel.py`
と同じ役割 ── 「knapsack_dp / greedy / branch_and_bound が小規模で最適を
出せているか」を裏取りする。移動距離も込みで評価する真の最適

計算量: O(vehicles ^ n_deliveries) 通りの割当 × 各車両内の巡回順最適化。
n_deliveries ≤ 8、vehicles ≤ 3 くらいまで(itertools.product が組合せ爆発する)。
`_ops` = 評価した割当の数。
"""

from __future__ import annotations

from itertools import product

from app.algorithms.optimization.logistics_common import (
    all_pairs,
    capacity_ok,
    infeasible_logistics_solution,
    logistics_solution,
    parse_logistics_problem,
    route_for_vehicle,
)
from app.domain.problems.problem import OptimizationProblem
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution


class BruteForceLogisticsStrategy:
    """配送先→車両の全割当を試して総距離最小の組合せを選ぶ(オラクル)。"""

    meta = AlgorithmMeta(
        name="brute_force",
        family="optimization",
        implementation="handwritten",
        time_complexity="O(vehicles^n * n!)",  # 割当 × 巡回順
        space_complexity="O(n)",
    )

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data, forbidden = parse_logistics_problem(problem)
        dist = all_pairs(data, forbidden)
        by_id = {d.id: d for d in data.deliveries}
        vehicles = data.vehicles
        deliveries = data.deliveries

        best_assignment: dict[str, list[str]] | None = None
        best_total = float("inf")
        ops = 0

        for choice in product(range(len(vehicles)), repeat=len(deliveries)):
            ops += 1
            buckets: dict[str, list[str]] = {v.id: [] for v in vehicles}
            for delivery, vi in zip(deliveries, choice, strict=True):
                buckets[vehicles[vi].id].append(delivery.id)

            total = 0.0
            feasible = True
            for vehicle in vehicles:
                ids = buckets[vehicle.id]
                if not ids:
                    continue
                stops = [by_id[i] for i in ids]
                if not capacity_ok(vehicle, stops):
                    feasible = False
                    break
                result = route_for_vehicle(data.depot_id, stops, dist)
                if result is None:
                    feasible = False
                    break
                _, distance = result
                total += distance
            if feasible and total < best_total:
                best_total = total
                best_assignment = {vid: ids for vid, ids in buckets.items() if ids}

        if best_assignment is None:
            return infeasible_logistics_solution(self.meta)
        return logistics_solution(data, best_assignment, dist, self.meta, ops=ops)
