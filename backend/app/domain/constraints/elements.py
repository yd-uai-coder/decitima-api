"""forbidden / required_inclusion が共有する「解が触れた要素 id 集合」の抽出。

解型ごとに「要素」の意味が変わる。route だけが node と edge を区別する
(必須経由地 = node、通行禁止 = edge)。network / travel は選択単位が 1 種類なので
aspect によらず同じ集合を返す。
"""

from __future__ import annotations

from typing import Literal

from app.domain.solutions.network_design import NetworkDesignSolution
from app.domain.solutions.route_planner import RouteSolution
from app.domain.solutions.solution import CandidateSolution
from app.domain.solutions.travel_planner import TravelSolution

# aspect: route 解でどの id 列を見るか。他の解型は選択単位が 1 種類なので無視される
type ElementAspect = Literal["nodes", "edges"]


def solution_element_ids(solution: CandidateSolution, *, aspect: ElementAspect) -> set[str] | None:
    """解が触れた要素の id 集合。forbidden / required_inclusion が扱えない解型は None。

    aspect: "nodes" … 訪問・経由した地点(required_inclusion 向き)/
            "edges" … 使った接続(forbidden 向き)。route 解でのみ nodes と異なる
    戻り値: 要素 id の集合。route / network / travel 以外の解型は None(チェッカーは素通し)
    """
    assignments = solution.assignments
    # route だけ node / edge を区別。他 2 型は選択単位が 1 種類
    if isinstance(assignments, RouteSolution):
        ids = assignments.path_node_ids if aspect == "nodes" else assignments.path_edge_ids
        return set(ids)
    if isinstance(assignments, NetworkDesignSolution):
        return set(assignments.selected_link_ids)
    if isinstance(assignments, TravelSolution):
        return set(assignments.selected_place_ids)
    return None
