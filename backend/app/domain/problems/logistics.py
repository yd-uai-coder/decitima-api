"""Logistics Optimizer の問題固有データ(葉モジュール)。

配送計画(CVRP)= 1 つのデポから複数車両が出発し、複数の配送先を分担して回ってデポに戻る問題。
各車両には容量(重量・体積の 2 次元)があり、各配送先には需要(重量・体積)がある。道路網は
一般グラフ(ノード + 区間)── route_planner.py の RouteData に近い構造で、Dijkstra/A* ではなく
Floyd-Warshallで全点対距離を前処理する(区間が多くないので密行列で十分)。

このファイルは兄弟モジュール(route_planner.py / travel_planner.py / project_manager.py 等)を
import しない。ユニオンの合成は problem.py(アグリゲータ)が行う。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class LogisticsNode(BaseModel):
    """道路網のノード1つ(交差点・拠点)。座標 x / y は任意(将来 A* を使う場合の予約)。"""

    id: str
    label: str | None = None
    x: float | None = None
    y: float | None = None


class RoadSegment(BaseModel):
    """道路区間1本。distance は距離または所要時間。route_planner.py の RouteEdge と同型だが、
    葉は兄弟を import しない設計(travel が TravelLeg を独自定義したのと同じ理由)で独立に持つ。
    """

    id: str
    source: str  # 端点ノードの id
    target: str  # 端点ノードの id
    distance: float = Field(ge=0)
    directed: bool = False  # False なら source <-> target の双方向(一方通行なら True)


class Vehicle(BaseModel):
    """配送車両1台。容量は重量・体積の2次元(Knapsack DP の2次元容量に対応)。"""

    id: str
    capacity_weight: float = Field(ge=0)
    capacity_volume: float = Field(ge=0)


class DeliveryStop(BaseModel):
    """配送先1件。node_id で道路網上の位置を指す(同じノードに複数の配送先があってもよい)。"""

    id: str
    node_id: str
    demand_weight: float = Field(ge=0)
    demand_volume: float = Field(ge=0)


class LogisticsData(BaseModel):
    """Logistics Optimizer の問題固有データ。道路網・デポ・車両群・配送先群。"""

    problem_type: Literal["logistics_planning"] = "logistics_planning"
    depot_id: str  # 出発・帰着ノードの id
    nodes: list[LogisticsNode]
    segments: list[RoadSegment]
    vehicles: list[Vehicle]
    deliveries: list[DeliveryStop]

    @model_validator(mode="after")
    def _refs_and_ids(self) -> LogisticsData:
        """depot / 区間端点 / 配送先の node_id が実在するか、id が一意か(Input Validation)。

        「デポから全配送先へ到達できるか」は BFS を走らせる計算なので services/validation.py が
        判定する(`Phase-2-2.md` §3「これは計算か? 述語か?」の 5 例目)。
        """
        node_ids = {n.id for n in self.nodes}
        if len(node_ids) != len(self.nodes):
            raise ValueError("duplicate node id(s)")
        if self.depot_id not in node_ids:
            raise ValueError(f"depot_id {self.depot_id!r} is not a node id")

        seg_ids = [s.id for s in self.segments]
        if len(seg_ids) != len(set(seg_ids)):
            raise ValueError("duplicate segment id(s)")
        bad_seg = [
            s.id for s in self.segments if s.source not in node_ids or s.target not in node_ids
        ]
        if bad_seg:
            raise ValueError(f"segment(s) {bad_seg} reference unknown node id(s)")
        loop_seg = [s.id for s in self.segments if s.source == s.target]
        if loop_seg:
            raise ValueError(f"segment(s) {loop_seg} are self-loops")

        vehicle_ids = [v.id for v in self.vehicles]
        if len(vehicle_ids) != len(set(vehicle_ids)):
            raise ValueError("duplicate vehicle id(s)")

        delivery_ids = [d.id for d in self.deliveries]
        if len(delivery_ids) != len(set(delivery_ids)):
            raise ValueError("duplicate delivery id(s)")
        bad_delivery = [d.id for d in self.deliveries if d.node_id not in node_ids]
        if bad_delivery:
            raise ValueError(f"delivery(ies) {bad_delivery} reference unknown node id(s)")
        return self
