"""Shift Scheduler の解(葉モジュール)。型のみ。解を作るのは Phase 5。設計は Phase-0-2.md §6。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel

# 割当: slot_id -> [staff_id, ...]。ShiftSolution.assignments の型であり、shift を解く / 検証する
# 全レイヤーの共有語彙。algorithms(scheduling/*)も domain(solutions/shift_metrics)もここから
# import する ── 両者が循環なしで届く唯一の家が domain の葉であるこのファイル(Phase 6-1)。
type Assignment = dict[str, list[str]]


class ShiftSolution(BaseModel):
    """Shift Scheduler の解。スロット id ごとに割り当てたスタッフ id のリスト。"""

    problem_type: Literal["shift_scheduling"] = "shift_scheduling"
    assignments: dict[str, list[str]]  # slot_id -> [staff_id, ...]
