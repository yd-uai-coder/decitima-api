"""route_planning ストラテジー共通の足回り。

Dijkstra / Bellman-Ford / A* は「区間の最短経路の求め方」だけが違い、あとは同じ:
  1. 制約から forbidden / required を集める
  2. 隣接リストを作る
  3. 必須経由地の順を決めて、区間ごとに最短経路を解いて連結する
  4. CandidateSolution に詰める

その「同じ」部分をここに集約する。`Segment`(1 区間の結果)と `plan_route`(区間を
つないでルート全体にする)が中心。各 strategy は `segment_fn`(区間ソルバ)だけを渡す。
"""

from __future__ import annotations

from collections.abc import Callable
from itertools import pairwise

from app.algorithms.graph.waypoints import optimize_waypoint_order
from app.domain.problems.problem import (
    ForbiddenConstraint,
    OptimizationProblem,
    RequiredInclusionConstraint,
)
from app.domain.solutions.route_planner import RouteSolution
from app.domain.solutions.solution import (
    AlgorithmMeta,
    CandidateSolution,
    ConstraintViolation,
)

# 区間ソルバ: (start, goal) -> (最短経路の Segment | 到達不能なら None, 操作回数)
type SegmentFn = Callable[[str, str], tuple["Segment | None", int]]


class Segment:
    """1 区間(始点→終点)の最短経路。"""

    __slots__ = ("node_ids", "edge_ids", "weight")

    def __init__(self, node_ids: list[str], edge_ids: list[str], weight: float) -> None:
        self.node_ids = node_ids  # 経由ノード id 列(start で始まり goal で終わる)
        self.edge_ids = edge_ids  # 使ったエッジ id 列(len = len(node_ids) - 1)
        self.weight = weight


class _SegmentCache:
    """区間を一度だけ解いてキャッシュする。順序最適化で同じ区間を何度も引くため。"""

    def __init__(self, segment_fn: SegmentFn) -> None:
        self._segment_fn = segment_fn
        self._memo: dict[tuple[str, str], Segment | None] = {}
        self.ops = 0  # 全区間ソルバの操作回数の合計(metrics["_ops"])

    def weight(self, a: str, b: str) -> float | None:
        seg = self.segment(a, b)
        return None if seg is None else seg.weight

    def segment(self, a: str, b: str) -> Segment | None:
        key = (a, b)
        if key not in self._memo:
            seg, ops = self._segment_fn(a, b)
            self.ops += ops
            self._memo[key] = seg
        return self._memo[key]


def collect_route_constraints(
    problem: OptimizationProblem,
) -> tuple[set[str], list[str]]:
    """制約リストから (禁止エッジ id 集合, 必須経由ノード id 列) を取り出す。"""
    forbidden: set[str] = set()
    required: list[str] = []
    for c in problem.constraints:
        if isinstance(c, ForbiddenConstraint):
            forbidden.update(c.items)
        elif isinstance(c, RequiredInclusionConstraint):
            required.extend(c.items)
    return forbidden, required


def plan_route(
    start: str, goal: str, required: list[str], segment_fn: SegmentFn
) -> tuple[Segment | None, int]:
    """必須経由地の順を最適化し、区間ごとに解いて 1 本のルートに連結する。

    どこかの区間がどの順でも繋がらなければ (None, ops)。
    """
    cache = _SegmentCache(segment_fn)
    order = optimize_waypoint_order(start, goal, required, cache.weight)
    if order is None:
        return None, cache.ops

    node_ids: list[str] = []
    edge_ids: list[str] = []
    total = 0.0
    for a, b in pairwise(order):
        seg = cache.segment(a, b)
        if seg is None:
            return None, cache.ops
        # 区間の先頭ノードは前区間の末尾と重複するので落とす
        node_ids.extend(seg.node_ids if not node_ids else seg.node_ids[1:])
        edge_ids.extend(seg.edge_ids)
        total += seg.weight
    return Segment(node_ids, edge_ids, total), cache.ops


def negative_weight_violation(algorithm: str) -> ConstraintViolation:
    """負辺を扱えないアルゴリズム(Dijkstra / A*)が負辺グラフを渡されたときの違反。"""
    return ConstraintViolation(
        constraint_kind="negative_weight",
        severity="hard",
        message=f"{algorithm} requires non-negative weights; use bellman_ford",
    )


def negative_cycle_violation() -> ConstraintViolation:
    """start から到達できる負閉路がある(最短経路が定義できない)ときの違反。"""
    return ConstraintViolation(
        constraint_kind="negative_cycle",
        severity="hard",
        message="graph has a negative-weight cycle reachable from start; no shortest path exists",
    )


def route_solution(
    seg: Segment | None,
    ops: int | None,
    meta: AlgorithmMeta,
    *,
    violations: list[ConstraintViolation] | None = None,
) -> CandidateSolution:
    """区間連結の結果(または None)を CandidateSolution に詰める。

    seg が None なら status="infeasible"。「hard 制約を満たすか」は Verification が別途判定するので
    ここでは valid のままにする。ops=None(ライブラリトラック)なら metrics に "_ops" を入れない。
    """
    ops_metric: dict[str, float] = {} if ops is None else {"_ops": float(ops)}
    if seg is None:
        return CandidateSolution(
            status="infeasible",
            assignments=RouteSolution(path_node_ids=[], path_edge_ids=[], total_weight=0.0),
            metrics=ops_metric,
            violations=violations or [],
            produced_by=meta,
        )
    return CandidateSolution(
        status="valid",
        assignments=RouteSolution(
            path_node_ids=seg.node_ids,
            path_edge_ids=seg.edge_ids,
            total_weight=seg.weight,
        ),
        metrics={"total_weight": seg.weight, **ops_metric},
        violations=violations or [],
        produced_by=meta,
    )

def reconstruct_path(prev: dict[str, tuple[str, str]], start: str, goal: str, weight: float) -> Segment:
    """prev を goal から辿って start→goal 順のノード列・エッジ列に直す。"""
    node_ids = [goal]
    edge_ids: list[str] = []
    while node_ids[-1] != start:
        p_node, p_edge = prev[node_ids[-1]]
        node_ids.append(p_node)
        edge_ids.append(p_edge)
    node_ids.reverse()
    edge_ids.reverse()
    return Segment(node_ids, edge_ids, weight)