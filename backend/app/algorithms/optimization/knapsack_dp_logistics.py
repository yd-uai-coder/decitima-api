"""KnapsackDpLogisticsStrategy(手実装、主力)── 容量だけを見て詰める上界。

`knapsack_2d`の 2 人目の消費者。車両を1台ずつ、残っている配送先から
「容量(重量×体積)に収まる部分集合」を Knapsack DP で選ぶ ── 価値は全アイテム均一 1.0 なので、
**台数当たりの搭載数を最大化する**(travel の「place cost だけで詰める」= 移動費用を無視した
上界と対になる、「容量だけで詰める」= **移動距離を無視した上界**)。選んだ後に
`logistics_common.route_for_vehicle`(TSP 近似の再利用)で巡回順と実際の距離を確定する。

容量そのものは knapsack_2d が厳密に守るので、travel/project と違って `invalid` にはならない
── ただし選んだ組合せが地理的に離れていれば、移動距離では `greedy` / `branch_and_bound` に
劣ることがある。

計算量: 車両ごとに O(残り配送先数 × capacity_weight × capacity_volume)(擬多項式)。
"""

from __future__ import annotations

import math

from app.algorithms.optimization.knapsack import Item, knapsack_2d
from app.algorithms.optimization.logistics_common import (
    all_pairs,
    infeasible_logistics_solution,
    logistics_solution,
    parse_logistics_problem,
)
from app.domain.problems.problem import OptimizationProblem
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution


class KnapsackDpLogisticsStrategy:
    """車両ごとに 2 次元ナップサック DP で配送先の部分集合を選ぶ手実装ストラテジー。"""

    meta = AlgorithmMeta(
        name="knapsack_dp",
        family="optimization",
        implementation="handwritten",
        time_complexity="O(vehicles * n * capacity_weight * capacity_volume)",  # 擬多項式
        space_complexity="O(n * capacity_weight * capacity_volume)",
    )

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data, forbidden = parse_logistics_problem(problem)
        dist = all_pairs(data, forbidden)

        remaining = {d.id: d for d in data.deliveries}
        assignment: dict[str, list[str]] = {}
        ops = 0

        for vehicle in data.vehicles:
            if not remaining: # 配送先残数がなければ終了
                break
            cap_a = math.floor(vehicle.capacity_weight)
            cap_b = math.floor(vehicle.capacity_volume)

            candidate_ids = list(remaining)
            items: list[Item] = []      # knapsack_2d に渡す「重み・重み・価値」の数値だけの配列
            kept_ids: list[str] = []    # items の各要素が「どの配送先id」だったかを覚えておく配列
            for did in candidate_ids:
                d = remaining[did]
                wa, wb = math.ceil(d.demand_weight), math.ceil(d.demand_volume)
                if wa > cap_a or wb > cap_b:
                    continue  # 単体でこの車両に載らない配送先は DP に入れない
                items.append((wa, wb, 1.0))  # 価値均一 ── 台数当たりの搭載数を最大化(距離は無視)
                kept_ids.append(did)
            
            picked_idx = set(knapsack_2d(items, cap_a, cap_b)) # 価値最大化のインデックス取得
            chosen = [kept_ids[i] for i in range(len(kept_ids)) if i in picked_idx]
            if not chosen:
                continue
            ops += len(items) * (cap_a + 1) * (cap_b + 1)  # DP セル更新回数の目安
            assignment[vehicle.id] = chosen

            # reaming(配送残)から削除する 
            # -> 次のループではこのループで選ばれなかったreamingから最適化して選ぶ
            # 結果、配送先が車両ごとに振り分けされる
            for did in chosen:
                del remaining[did]

        if remaining:
            return infeasible_logistics_solution(self.meta)  # 車両を使い切っても運びきれない
        return logistics_solution(data, assignment, dist, self.meta, ops=ops)
