# DeciTima samples │ Phase 7
"""作業単位 7-3: Travel Planner の解(葉モジュール)。設計は README §12.3 / §19 Phase 7。

旅行プラン = 「訪れる place の集合」+「巡回順」+ 予実の合計値。
このファイルは兄弟葉を import しない。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class TravelSolution(BaseModel):
    """Travel Planner の解。訪れる place の集合と巡回順、効用・費用・時間の合計。"""

    problem_type: Literal["travel_planning"] = "travel_planning"
    selected_place_ids: list[str]  # 訪れる place の id 集合
    visit_order: list[str]  # 巡回順(selected_place_ids の順列。start があれば先頭)
    total_value: float  # 好み加重の効用合計(Σ value * preference)
    total_cost: float  # place cost + 区間 travel_cost の合計
    total_time: float  # place duration + 区間 travel_time の合計
