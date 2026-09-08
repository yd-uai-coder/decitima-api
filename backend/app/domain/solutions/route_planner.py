"""Route Planner の解(葉モジュール)。設計は Phase-0-2.md §6。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class RouteSolution(BaseModel):
    """Route Planner の解。start から goal までのノード列とエッジ列。"""

    problem_type: Literal["route_planning"] = "route_planning"
    path_node_ids: list[str]  # 経由順のノード id 列(start で始まり goal で終わる)
    path_edge_ids: list[str]  # 使用したエッジ id 列(len = len(path_node_ids) - 1)
    total_weight: float  # path_edge_ids の weight 合計
