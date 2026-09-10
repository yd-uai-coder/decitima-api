"""Travel Planner ストラテジー共通の足回り(`graph/mst.py` と同型)。

TravelData / TravelSolutionを受け、Floyd-Warshallで全点対距離を
前処理する ── ドメイン葉が揃うので新規作成。

Knapsack DP / Greedy / BruteForce は「訪問地の選び方」だけが違う。共通部分をここに集約:
  - `parse_travel_problem` … TravelData と forbidden / required の place id を取り出す
  - `place_utility`         … 好み係数を掛けた効用(value * preferences.get(id, 1.0))
  - `order_and_cost`        … 選んだ place の巡回順と、place + 移動を合わせた総費用・総時間
  - `travel_solution`       … 選んだ place 集合を CandidateSolution に詰める

`order_and_cost` は Floyd-Warshall(`graph/floyd_warshall.py`)で全点対距離を前処理し、
`optimize_waypoint_order`(`graph/waypoints.py`)で閉路(anchor に戻る)の順を決める。
「Floyd-Warshall は訪問順最適化の前処理」の実体。
"""

from __future__ import annotations

from app.algorithms.graph.adjacency import Adjacency, build_leg_adjacency
from app.algorithms.graph.floyd_warshall import AllPairs, floyd_warshall
from app.algorithms.graph.waypoints import optimize_waypoint_order
from app.domain.problems.problem import (
    ForbiddenConstraint,
    OptimizationProblem,
    RequiredInclusionConstraint,
)
from app.domain.problems.travel_planner import Place, TravelData
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution
from app.domain.solutions.travel_planner import TravelSolution


def parse_travel_problem(
    problem: OptimizationProblem,
) -> tuple[TravelData, set[str], set[str]]:
    """(TravelData, 使えない place id, 必須 place id) を返す。"""
    data = problem.data
    if not isinstance(data, TravelData):
        raise TypeError(f"expected TravelData, got {type(data).__name__}")
    forbidden: set[str] = set()
    required: set[str] = set()
    for c in problem.constraints:
        if isinstance(c, ForbiddenConstraint):
            forbidden.update(c.items)
        elif isinstance(c, RequiredInclusionConstraint):
            required.update(c.items)
    return data, forbidden, required


def place_utility(data: TravelData, place_id: str) -> float:
    """好み係数を掛けた効用。preferences 未指定の place は係数 1.0。"""
    place = _by_id(data)[place_id]
    return place.value * data.preferences.get(place_id, 1.0)


def _time_adjacency(data: TravelData, forbidden_leg_ids: set[str]) -> Adjacency:
    """移動 *時間* の隣接リスト(build_leg_adjacency は費用側)。"""
    adjacency: Adjacency = {p.id: [] for p in data.places}
    for leg in data.legs:
        if leg.id in forbidden_leg_ids:
            continue
        a, b = leg.endpoints
        adjacency.setdefault(a, []).append((b, leg.id, leg.travel_time))
        adjacency.setdefault(b, []).append((a, leg.id, leg.travel_time))
    return adjacency


def all_pairs(data: TravelData) -> tuple[AllPairs, AllPairs]:
    """(移動費用の全点対距離, 移動時間の全点対距離)。strategy が 1 度計算して使い回す。"""
    cost_dist = floyd_warshall(build_leg_adjacency(data, set()))
    time_dist = floyd_warshall(_time_adjacency(data, set()))
    return cost_dist, time_dist


def order_and_cost(
    data: TravelData, selected_ids: list[str], cost_dist: AllPairs, time_dist: AllPairs
) -> tuple[list[str], float, float] | None:
    """選んだ place を回る順(閉路)と、place cost/duration + 移動 cost/time の合計。

    どの順でも全部を繋げないなら None。`data.start` があればそこを anchor にし、必ず含める。
    """
    sel = list(dict.fromkeys(selected_ids))  # 重複除去・順序保持
    if data.start is not None and data.start not in sel:
        sel = [data.start, *sel]
    if not sel:
        return [], 0.0, 0.0

    anchor = data.start if data.start in sel else sel[0]
    rest = [p for p in sel if p != anchor]
    tour = optimize_waypoint_order(anchor, anchor, rest, lambda a, b: _finite(cost_dist[a][b]))
    if tour is None:
        return None  # anchor から全 place を回れない

    visit = tour[:-1] if len(tour) > 1 and tour[0] == tour[-1] else tour
    cost, time = tour_cost(data, visit, cost_dist, time_dist)
    return visit, cost, time


def tour_cost(
    data: TravelData, visit: list[str], cost_dist: AllPairs, time_dist: AllPairs
) -> tuple[float, float]:
    """*与えられた順* `visit` を回る閉路(最後に出発地へ戻る)の総費用・総時間。

    place cost/duration + 区間の移動 cost/time。順は再最適化しない ── Verification が
    「strategy の申告した順のコスト」を検算するのに使う。
    """
    by_id = _by_id(data)
    place_cost = sum(by_id[p].cost for p in visit if p in by_id)
    place_time = sum(by_id[p].duration for p in visit if p in by_id)
    if len(visit) <= 1:
        return place_cost, place_time
    closed = [*visit, visit[0]]  # 出発地に戻る閉路
    travel_cost = sum(cost_dist[a][b] for a, b in zip(closed, closed[1:], strict=False))
    travel_time = sum(time_dist[a][b] for a, b in zip(closed, closed[1:], strict=False))
    return place_cost + travel_cost, place_time + travel_time


def travel_solution(
    data: TravelData,
    selected_ids: list[str],
    cost_dist: AllPairs,
    time_dist: AllPairs,
    ops: int | None,
    meta: AlgorithmMeta,
) -> CandidateSolution:
    """選んだ place 集合を CandidateSolution に詰める。順序と総コストは order_and_cost が計算。

    ops=None(理論上ありうるライブラリトラック)なら metrics に "_ops" を入れない。
    予算・時間の hard 判定は Verification が行う ── ここでは status="valid" で返す
    (回れないなら "infeasible")。
    """
    ops_metric: dict[str, float] = {} if ops is None else {"_ops": float(ops)}
    ordered = order_and_cost(data, selected_ids, cost_dist, time_dist)
    if ordered is None:
        return CandidateSolution(
            status="infeasible",
            assignments=TravelSolution(
                selected_place_ids=[],
                visit_order=[],
                total_value=0.0,
                total_cost=0.0,
                total_time=0.0,
            ),
            metrics=ops_metric,
            produced_by=meta,
        )
    visit, total_cost, total_time = ordered
    total_value = sum(place_utility(data, p) for p in visit)
    return CandidateSolution(
        status="valid",
        assignments=TravelSolution(
            selected_place_ids=list(visit),
            visit_order=list(visit),
            total_value=total_value,
            total_cost=total_cost,
            total_time=total_time,
        ),
        metrics={
            "total_value": total_value,
            "total_cost": total_cost,
            "total_time": total_time,
            **ops_metric,
        },
        produced_by=meta,
    )


# --- 内部ヘルパ -------------------------------------------------------------


def _by_id(data: TravelData) -> dict[str, Place]:
    return {p.id: p for p in data.places}


def _finite(x: float) -> float | None:
    """math.inf(到達不能)を optimize_waypoint_order 向けに None へ。"""
    return None if x == float("inf") else x
