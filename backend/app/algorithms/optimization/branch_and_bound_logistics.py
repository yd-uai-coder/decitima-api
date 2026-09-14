# DeciTima samples │ Phase 9
"""BranchAndBoundLogisticsStrategy(分枝限定法)── 確定距離を下界に、
配送先→車両の割当を DFS + 分枝限定で探索する。

下界(lower bound): **これまでに確定した距離**をそのまま使う。容量制約下の TSP は
三角不等式を満たす(Floyd-Warshall の距離は定義上そう)ので、車両に配送先を1件足すと
その車両の最適巡回距離は単調に非減少 ── 「確定済みの合計距離」は真の最終距離を絶対に
上回らない、安全(admissible)だが緩い下界になる。

より tight な下界(残りの配送先をデポからの片道距離の総和で見積もる、等)は経路の共有を
過小評価しかねず、admissible 性を保証するには慎重な議論が要る ── 発展課題として残す
(`_lower_bound` が labor_cost の楽観推定を使ったのと同じ精神だが、ここでは
「常に安全」側を優先した)。

決定論的 anytime と同じく壁時計ではなく**展開ノード数の予算** `_MAX_NODES` で
打ち切る。予算切れ時はその時点の最良解を `metrics["_truncated"]=1.0` 付きで返す。

`_ops` = 展開ノード数。
"""

from __future__ import annotations

from app.algorithms.graph.floyd_warshall import AllPairs
from app.algorithms.optimization.logistics_common import (
    all_pairs,
    capacity_ok,
    infeasible_logistics_solution,
    logistics_solution,
    parse_logistics_problem,
    route_for_vehicle,
)
from app.domain.problems.logistics import LogisticsData
from app.domain.problems.problem import OptimizationProblem
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution

# 決定論的なノード予算。これを超えたら最良解 + _truncated で打ち切る(Phase 6 の 2 人目の消費者)。
_MAX_NODES = 200_000


class BranchAndBoundLogisticsStrategy:
    """手実装の分枝限定法(implementation="handwritten")。"""

    meta = AlgorithmMeta(
        name="branch_and_bound",
        family="optimization",
        implementation="handwritten",
        time_complexity="最悪 O(vehicles^n)、確定距離の下界で枝刈り",
        space_complexity="O(n)",
    )

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data, forbidden = parse_logistics_problem(problem)
        dist = all_pairs(data, forbidden)
        search = _Search(data, dist)
        search.run()
        if search.best is None:
            return infeasible_logistics_solution(self.meta)
        sol = logistics_solution(data, search.best, dist, self.meta, ops=search.ops)
        if search.truncated:
            sol = sol.model_copy(update={"metrics": {**sol.metrics, "_truncated": 1.0}})
        return sol


class _Search:
    def __init__(self, data: LogisticsData, dist: AllPairs) -> None:
        self._data = data
        self._dist = dist
        self._deliveries = sorted(data.deliveries, key=lambda d: d.id)
        self._by_id = {d.id: d for d in data.deliveries}
        self._vehicles = data.vehicles

        self.best: dict[str, list[str]] | None = None
        self.best_total = float("inf")
        self.ops = 0
        self.truncated = False

    def run(self) -> None:
        buckets: dict[str, list[str]] = {v.id: [] for v in self._vehicles}
        distances: dict[str, float] = {v.id: 0.0 for v in self._vehicles}
        self._recurse(0, buckets, distances, confirmed=0.0)

    def _recurse(
        self,
        i: int,
        buckets: dict[str, list[str]],
        distances: dict[str, float],
        confirmed: float,
    ) -> None:
        if self.ops >= _MAX_NODES:
            self.truncated = True
            return
        self.ops += 1
        if confirmed >= self.best_total:
            return  # 確定距離は単調非減少 ── 下界が現最良以上なら枝刈り

        if i == len(self._deliveries):
            self.best_total = confirmed
            self.best = {vid: list(ids) for vid, ids in buckets.items() if ids}
            return

        delivery = self._deliveries[i]
        for vehicle in self._vehicles:
            if self.ops >= _MAX_NODES:
                self.truncated = True
                return
            trial_ids = [*buckets[vehicle.id], delivery.id]
            trial_stops = [self._by_id[j] for j in trial_ids]
            if not capacity_ok(vehicle, trial_stops):
                continue  # 容量オーバーの分枝は伸ばさない
            result = route_for_vehicle(self._data.depot_id, trial_stops, self._dist)
            if result is None:
                continue
            _, new_distance = result

            old_distance = distances[vehicle.id]
            buckets[vehicle.id].append(delivery.id)
            distances[vehicle.id] = new_distance
            self._recurse(i + 1, buckets, distances, confirmed - old_distance + new_distance)
            buckets[vehicle.id].pop()
            distances[vehicle.id] = old_distance
