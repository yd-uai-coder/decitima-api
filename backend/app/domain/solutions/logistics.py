"""Logistics Optimizer の解(葉モジュール)。

解 = 車両ごとの配送先訪問順(VehicleRoute)の集まり。使わない車両は routes に含めない。
このファイルは兄弟葉を import しない。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class VehicleRoute(BaseModel):
    """1台の車両が回る配送先の列。デポは含まない(必ずデポで折り返す前提のため暗黙)。"""

    vehicle_id: str
    stop_ids: list[str]  # この車両が訪れる配送先(DeliveryStop.id)の訪問順
    distance: float  # デポ発 → 訪問順 → デポ着の往復距離


class LogisticsSolution(BaseModel):
    """Logistics Optimizer の解。使った車両ぶんの VehicleRoute と、その距離の合計。"""

    problem_type: Literal["logistics_planning"] = "logistics_planning"
    routes: list[VehicleRoute]
    total_distance: float  # Σ route.distance(構造検証で整合を確認)
