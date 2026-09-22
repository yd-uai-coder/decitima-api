"""GreedyLogisticsStrategy(貪欲法)── 実際の距離増分が最小の車両へ1件ずつ足す。

KnapsackDpLogisticsStrategy との違い: DP は「容量だけを見た上界」(移動距離は無視)を出すが、
Greedy は **1 件足すたびに実際の巡回順・往復距離を計算し直して**、増分が最小の車両を選ぶ。
容量オーバーの候補は最初から除外するので必ず valid(travel の GreedyTravelStrategy と同じ
「実消費を見ながら詰める」設計)。

`_ops` = (配送先, 車両) の組み合わせを試した回数。
"""

from __future__ import annotations

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


class GreedyLogisticsStrategy:
    """配送先を1件ずつ、挿入したときの距離増分が最小の車両へ足す手実装ストラテジー。"""

    meta = AlgorithmMeta(
        name="greedy",
        family="optimization",
        implementation="handwritten",
        time_complexity="O(n^2 * vehicles * (m log m))",  # 挿入のたびに route_for_vehicle(内部TSP)
        space_complexity="O(n)",
    )

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data, forbidden = parse_logistics_problem(problem)
        dist = all_pairs(data, forbidden)
        by_id = {d.id: d for d in data.deliveries}

        assignment: dict[str, list[str]] = {v.id: [] for v in data.vehicles}
        current_distance: dict[str, float] = {v.id: 0.0 for v in data.vehicles}
        ops = 0

        for delivery in sorted(data.deliveries, key=lambda d: d.id):
            best_vehicle: str | None = None
            best_increase = float("inf")
            for vehicle in data.vehicles:
                ops += 1
                trial_ids = [*assignment[vehicle.id], delivery.id]
                trial_stops = [by_id[i] for i in trial_ids]
                if not capacity_ok(vehicle, trial_stops):
                    continue  # 容量オーバーの候補は最初から除外 ── 必ず valid になる理由
                result = route_for_vehicle(data.depot_id, trial_stops, dist)
                if result is None:
                    continue
                _, distance = result
                increase = distance - current_distance[vehicle.id]
                if increase < best_increase:
                    best_increase, best_vehicle = increase, vehicle.id
            if best_vehicle is None:
                return infeasible_logistics_solution(self.meta)  # どの車両にも積めない
            assignment[best_vehicle].append(delivery.id)
            current_distance[best_vehicle] += best_increase

        return logistics_solution(data, assignment, dist, self.meta, ops=ops)
