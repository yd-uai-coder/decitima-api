# DeciTima samples │ Phase 7
"""作業単位 7-3: Travel Planner の問題固有データ(葉モジュール)。設計は README §12.3 / §19 Phase 7。

旅行プラン = 訪問候補地(place)から予算・時間内で好み加重の効用が最大になる部分集合を選び、
その巡回順を決める問題。place 間の移動は無向の leg(区間)で与え、全点対距離は Floyd-Warshall
で前処理する(`algorithms/graph/floyd_warshall.py`)。

このファイルは兄弟葉(route_planner.py / shift_scheduler.py / network_design.py)を import しない。
ユニオンの合成は problem.py(アグリゲータ)が行う。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class Place(BaseModel):
    """訪問候補地1つ。value は基本効用、preferences(TravelData 側)が係数で乗る。"""

    id: str
    name: str | None = None
    value: float  # 基本効用(訪れる価値)。負でもよい(嫌々寄る場所)
    cost: float = Field(ge=0)  # 入場料など、その場所で使う費用
    duration: float = Field(ge=0)  # 滞在時間


class TravelLeg(BaseModel):
    """place 間の移動区間1本。常に無向(行き帰りで同じ)。"""

    id: str
    endpoints: tuple[str, str]  # 接続する 2 place の id
    travel_cost: float = Field(ge=0)  # 移動にかかる費用(交通費)
    travel_time: float = Field(ge=0)  # 移動にかかる時間


class TravelData(BaseModel):
    """Travel Planner の問題固有データ。訪問候補・移動グラフ・予算・時間・好み。"""

    problem_type: Literal["travel_planning"] = "travel_planning"
    places: list[Place]
    legs: list[TravelLeg]
    budget: float = Field(ge=0)  # 使える総費用(place cost + 移動 cost の上限)
    time_budget: float = Field(ge=0)  # 使える総時間(place duration + 移動 time の上限)
    start: str | None = None  # 起点 place の id(任意)。あれば巡回順はここから始まる
    # place_id -> 好み係数。効用 = value * preferences.get(id, 1.0)。未指定は 1.0
    preferences: dict[str, float] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _refs_exist(self) -> TravelData:
        """leg 端点 / start / preferences のキーが places に実在するか(Input Validation)。"""
        ids = {p.id for p in self.places}
        bad_legs = [
            leg.id
            for leg in self.legs
            if leg.endpoints[0] not in ids or leg.endpoints[1] not in ids
        ]
        if bad_legs:
            raise ValueError(f"leg(s) {bad_legs} reference unknown place id(s)")
        if self.start is not None and self.start not in ids:
            raise ValueError(f"start={self.start!r} is not a place id")
        bad_pref = [k for k in self.preferences if k not in ids]
        if bad_pref:
            raise ValueError(f"preferences key(s) {bad_pref} are not place ids")
        return self
