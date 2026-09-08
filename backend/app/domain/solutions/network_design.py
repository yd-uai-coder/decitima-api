"""Network Designer の解(葉モジュール)。設計は Phase-0-2.md §8.1。

MST は「選んだリンクの集合」で表す(route の「ノード列 + エッジ列」とは形が違う)。
このファイルは兄弟(route_planner.py / shift_scheduler.py)を import しない。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class NetworkDesignSolution(BaseModel):
    """Network Designer の解。全拠点を繋ぐために敷設するリンクの集合と総コスト。"""

    problem_type: Literal["network_design"] = "network_design"
    selected_link_ids: list[str]  # 敷設するリンクの id 集合(全域木なら len = ノード数 - 1)
    total_weight: float  # selected_link_ids の weight 合計
