"""必須経由地の訪問順最適化(プリミティブ)。

- 経由地が `_MAX_EXACT`(=8)以下: 全順列を試し、区間距離の和が最小の順を選ぶ
- それより多い: 与えられた順のまま(近似は Phase 7 Travel Planner)

区間の最短距離そのものは呼び出し側(strategy)が `cost` 関数として渡す ── この関数は
グラフアルゴリズムに依存しない純粋なロジック(順列を回すだけ)。
"""

from __future__ import annotations

from collections.abc import Callable
from itertools import pairwise, permutations

# 経由地がこの数以下なら全順列を試す。9! ≈ 36 万なのでここで線を引く
_MAX_EXACT = 8

# 区間コスト関数: (a, b) -> a から b への最短距離。到達不能なら None
type SegmentCost = Callable[[str, str], float | None]


def optimize_waypoint_order(
    start: str, goal: str, required: list[str], cost: SegmentCost
) -> list[str] | None:
    """[start, (必須を最適順に), goal] のノード列を返す。

    どの順でも start→…→goal が繋がらない(全順列で区間が None)なら None。
    required の重複・start/goal との重複は畳む。
    """
    # 重複除去(初出順を保持)。start / goal と同じものは経由地から外す
    seen: dict[str, None] = {}
    for w in required:
        if w not in (start, goal):
            seen.setdefault(w, None)
    waypoints = list(seen)

    if not waypoints:
        return _collapse([start, goal])

    # 経由地の数で分岐
    # _exact_bestと_approx_bestは共通してstartからgoalへの到達不可能な場合にNoneを返す
    if len(waypoints) <= _MAX_EXACT:
        best_order = _exact_best(start, goal, waypoints, cost)
    else:
        best_order = _approx_best(start, goal, waypoints, cost)

    return None if best_order is None else _collapse(best_order)


def _exact_best(start: str, goal: str, waypoints: list[str], cost: SegmentCost) -> list[str] | None:
    """全順列を試して区間コスト和が最小の [start, ..., goal] を返す。
       「経由地をどの順に並べても start→…→goal を繋げない」とき。はNone
    """
    best_order: list[str] | None = None
    best_total = float("inf")
    for perm in permutations(waypoints):
        seq = [start, *perm, goal]
        total = _path_total(seq, cost)
        if total is not None and total < best_total:
            best_total = total
            best_order = seq
    return best_order


def _approx_best(
    start: str, goal: str, waypoints: list[str], cost: SegmentCost
) -> list[str] | None:
    """最近傍法で初期順を作り、2-opt で局所改善する。厳密性は保証しない。"""
    # --- 最近傍法: start から「未訪問で一番近い経由地」を繰り返し選ぶ ---
    remaining = set(waypoints)
    order: list[str] = []
    current = start
    while remaining:
        nxt = min(
            remaining,
            key=lambda w: _inf_if_none(cost(current, w)),
        )
        if cost(current, nxt) is None:
            break  # どこにも繋がらない ── 局所探索に回して繋がる順を探す
        order.append(nxt)
        remaining.discard(nxt)
        current = nxt
    if remaining:
        order.extend(remaining)  # 繋がらなかった分は末尾に(2-opt が並べ替える)

    # --- 2-opt: 区間 [i, j] を反転して総和が縮むなら採用。改善が止まるまで ---
    seq = [start, *order, goal]
    improved = True
    while improved:
        improved = False
        for i in range(1, len(seq) - 2):
            for j in range(i + 1, len(seq) - 1):
                cand = seq[:i] + seq[i : j + 1][::-1] + seq[j + 1 :]
                before, after = _path_total(seq, cost), _path_total(cand, cost)
                if after is not None and (before is None or after < before):
                    seq = cand
                    improved = True
    return seq if _path_total(seq, cost) is not None else None


def _path_total(seq: list[str], cost: SegmentCost) -> float | None:
    """seq を順に辿った区間コストの和。1 区間でも None なら None(不通)。"""
    total = 0.0
    for a, b in pairwise(seq):
        d = cost(a, b)
        if d is None:
            return None
        total += d
    return total


def _inf_if_none(x: float | None) -> float:
    return float("inf") if x is None else x


def _collapse(seq: list[str]) -> list[str]:
    """連続する重複を1つに畳む([A, A, B] -> [A, B])。"""
    out: list[str] = []
    for x in seq:
        if not out or out[-1] != x:
            out.append(x)
    return out