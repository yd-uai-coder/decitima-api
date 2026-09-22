"""Logistics strategy 共通の足回り(`travel_common.py` / `project_common.py` と同型)。

LogisticsData / LogisticsSolutionを受け、Floyd-Warshallで全点対距離を
前処理する

knapsack_dp / greedy / branch_and_bound / brute_force / pulp_milp は「配送先→車両の割当」の
決め方だけが違う。共通部分をここに集約:
  - `parse_logistics_problem` … LogisticsData と forbidden 区間 id を取り出す
  - `all_pairs`               … 道路網全体の全点対距離(Floyd-Warshall。1 度計算して使い回す)
  - `capacity_ok`             … 配送先の集まりが1台の車両に収まるか(重量・体積の両方)
  - `route_for_vehicle`       … 1 台分の配送先を回る最適順(TSP 近似の再利用)と往復距離
  - `route_distance`          … *与えられた順*(検算用。strategy の申告順を再最適化しない)
  - `logistics_solution`      … 車両ごとの配送先の集まりを CandidateSolution に詰める

`route_for_vehicle` は `optimize_waypoint_order`(`graph/waypoints.py`)を depot を起点 = 終点の
閉路として呼ぶ ── travel の `order_and_cost` が anchor に戻る閉路として呼ぶのと同じ使い方。
"""

from __future__ import annotations

from collections.abc import Mapping

from app.algorithms.graph.adjacency import build_logistics_adjacency
from app.algorithms.graph.floyd_warshall import AllPairs, floyd_warshall
from app.algorithms.graph.waypoints import optimize_waypoint_order
from app.domain.problems.logistics import DeliveryStop, LogisticsData, Vehicle
from app.domain.problems.problem import ForbiddenConstraint, OptimizationProblem
from app.domain.solutions.logistics import LogisticsSolution, VehicleRoute
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution


def parse_logistics_problem(problem: OptimizationProblem) -> tuple[LogisticsData, set[str]]:
    """(LogisticsData, 使えない道路区間 id) を返す。"""
    data = problem.data
    if not isinstance(data, LogisticsData):
        raise TypeError(f"expected LogisticsData, got {type(data).__name__}")
    forbidden = {
        item for c in problem.constraints if isinstance(c, ForbiddenConstraint) for item in c.items
    }
    return data, forbidden


def all_pairs(data: LogisticsData, forbidden_segment_ids: set[str]) -> AllPairs:
    """道路網全体の全点対距離。strategy が 1 度計算して使い回す(travel の all_pairs と同型)。"""
    return floyd_warshall(build_logistics_adjacency(data, forbidden_segment_ids))


def capacity_ok(vehicle: Vehicle, stops: list[DeliveryStop]) -> bool:
    """stops を 1 台の vehicle にまとめて積めるか(重量・体積の両方を満たす必要がある)。"""
    return (
        sum(s.demand_weight for s in stops) <= vehicle.capacity_weight
        and sum(s.demand_volume for s in stops) <= vehicle.capacity_volume
    )


def route_for_vehicle(
    depot_id: str, stops: list[DeliveryStop], dist: AllPairs
) -> tuple[list[str], float] | None:
    """1 台分の配送先(stops)を回る最短順と、デポで折り返す往復距離。

    同じノードに複数配送先があってもよい ── TSP はノード単位で解き、配送先はノードの並びに
    沿って束ねて展開する。どの順でもデポから全ノードを回れないなら None。

    """
    if not stops:
        return [], 0.0
    by_node: dict[str, list[str]] = {}
    for s in stops:
        by_node.setdefault(s.node_id, []).append(s.id) 

    # node順の最適化
    node_order = optimize_waypoint_order(
        depot_id, depot_id, list(by_node), cost=lambda a, b: _finite(dist[a][b])
    )
    if node_order is None:
        return None

    # node_order は必ず [depot, ...訪問順..., depot] の閉路(depot を起点=終点にして呼んでいるため)。
    # 中間だけが実際の訪問順 ── 写経の罠: node_order[:-1] だけだと先頭の depot が residual で残る。
    visit_nodes = node_order[1:-1] if len(node_order) > 1 else []
    stop_ids = [sid for node in visit_nodes for sid in by_node[node]]
    return stop_ids, route_distance(depot_id, visit_nodes, dist)


def route_distance(depot_id: str, node_order: list[str], dist: AllPairs) -> float:
    """与えられた訪問順(ノード列、depot は含まない)をデポで折り返す閉路として辿った距離。

    順序は検算対象(strategy の申告順)であり、ここでは再最適化しない
    (`travel_common.tour_cost` と同じ契約 ── Verification が使う)。
    """
    if not node_order:
        return 0.0
    closed = [depot_id, *node_order, depot_id]
    return sum(dist[a][b] for a, b in zip(closed, closed[1:], strict=False))


def logistics_solution(
    data: LogisticsData,
    assignment: Mapping[str, list[str]],
    dist: AllPairs,
    meta: AlgorithmMeta,
    *,
    ops: int | None,
) -> CandidateSolution:
    """vehicle ごとの配送先集合(assignment: vehicle_id -> delivery id 群)を、実際に回る順+距離へ
    確定して CandidateSolution に詰める。どれか 1 台でも回れない(None)なら infeasible。
    全配送先が割り当て済みという前提は呼び出し側(strategy)が保証する。
    """
    by_id = {s.id: s for s in data.deliveries}
    routes: list[VehicleRoute] = []
    for vehicle_id, delivery_ids in assignment.items():
        if not delivery_ids:
            continue  # 使わない車両は routes に含めない
        stops = [by_id[i] for i in delivery_ids]
        result = route_for_vehicle(data.depot_id, stops, dist)
        if result is None:
            return infeasible_logistics_solution(meta)
        stop_ids, distance = result
        routes.append(VehicleRoute(vehicle_id=vehicle_id, stop_ids=stop_ids, distance=distance))

    total_distance = sum(r.distance for r in routes)
    ops_metric: dict[str, float] = {} if ops is None else {"_ops": float(ops)}
    return CandidateSolution(
        status="valid",
        assignments=LogisticsSolution(routes=routes, total_distance=total_distance),
        metrics={
            "total_distance": total_distance,
            "vehicles_used": float(len(routes)),
            **ops_metric,
        },
        produced_by=meta,
    )


def infeasible_logistics_solution(meta: AlgorithmMeta) -> CandidateSolution:
    """全配送先を割り当てきれない / 回りきれないときの候補解。"""
    return CandidateSolution(
        status="infeasible",
        assignments=LogisticsSolution(routes=[], total_distance=0.0),
        metrics={},
        produced_by=meta,
    )


def _finite(x: float) -> float | None:
    """math.inf(到達不能)を optimize_waypoint_order 向けに None へ(travel_common と同じ変換)。"""
    return None if x == float("inf") else x
