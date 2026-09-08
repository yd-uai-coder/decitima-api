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
    if len(waypoints) > _MAX_EXACT:
        # 多すぎるので順序最適化はしない(与えられた順)
        return _collapse([start, *waypoints, goal])

    best_order: list[str] | None = None
    best_total = float("inf")
    for perm in permutations(waypoints):
        seq = [start, *perm, goal]
        total = 0.0
        ok = True
        for a, b in pairwise(seq):
            d = cost(a, b)
            if d is None:
                ok = False  # この順では区間 a→b が繋がらない
                break
            total += d
        if ok and total < best_total:
            best_total = total
            best_order = seq
    return None if best_order is None else _collapse(best_order)


def _collapse(seq: list[str]) -> list[str]:
    """連続する重複を1つに畳む([A, A, B] -> [A, B])。"""
    out: list[str] = []
    for x in seq:
        if not out or out[-1] != x:
            out.append(x)
    return out
