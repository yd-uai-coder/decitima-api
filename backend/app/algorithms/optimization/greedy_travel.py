"""GreedyTravelStrategy(貪欲法)── 効率(効用 ÷ かかるコスト)の高い place から詰める。

Knapsack DP との違い: DP は「移動を無視した上界」を出すが、Greedy は **1 つ選ぶたびに
実際の巡回順・移動費用・移動時間を計算し直して**、予算・時間に収まる範囲で貪欲に足す。
移動を織り込む代わりに最適性は保証しない ── この差を 7-6 の analysis で DP と並べる。

`_ops` = place を追加候補として評価した回数。
"""

from __future__ import annotations

from app.algorithms.optimization.travel_common import (
    all_pairs,
    order_and_cost,
    parse_travel_problem,
    place_utility,
    travel_solution,
)
from app.domain.problems.problem import OptimizationProblem
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution


class GreedyTravelStrategy:
    """効率順に place を足し、予算・時間を実消費しながら詰める手実装ストラテジー。"""

    meta = AlgorithmMeta(
        name="greedy",
        family="optimization",
        implementation="handwritten",
        time_complexity="O(n^2 * (n log n))",  # 毎回 order_and_cost(内部で順列/2-opt)
        space_complexity="O(n^2)",
    )

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        # problemから(TravelData, 禁止ノード, 必須ノード)を抽出
        data, forbidden, required = parse_travel_problem(problem)

        #TravelDataから費用と時間の隣接リストを作成
        cost_dist, time_dist = all_pairs(data)

        selected: list[str] = [rid for rid in sorted(required) if rid not in forbidden]
        remaining = [p.id for p in data.places if p.id not in forbidden and p.id not in selected]
        ops = 0

        # 改善がなくなるまでループする
        improved = True
        while improved:
            improved = False
            best_gain = 0.0
            best_id: str | None = None
            base = order_and_cost(data, selected, cost_dist, time_dist)
            base_cost = base[1] if base else 0.0
            base_time = base[2] if base else 0.0
            for pid in remaining:
                ops += 1
                trial = order_and_cost(data, [*selected, pid], cost_dist, time_dist)
                if trial is None:
                    continue
                _, cost, time = trial
                if cost > data.budget or time > data.time_budget:
                    continue  # 入れると予算 or 時間オーバー
                spent = (cost - base_cost) + (time - base_time)  # 追加でかかる資源
                gain = place_utility(data, pid) / spent if spent > 0 else place_utility(data, pid)
                if gain > best_gain:
                    best_gain, best_id = gain, pid
            if best_id is not None:
                selected.append(best_id)
                remaining.remove(best_id)
                improved = True

        return travel_solution(data, selected, cost_dist, time_dist, ops, self.meta)
