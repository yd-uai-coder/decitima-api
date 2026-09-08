"""シフト解の metrics 計算(domain ── 純粋)。

「この割当の人件費 / 希望休の達成率 / 勤務時間の均等度はいくつか」を計算する **唯一の場所**。
2 系統の消費者がこの同じコードを呼ぶので、数値は定義上ズレない(drift しない):

  - Verification … `structure.verify_shift_structure` が最終解の metrics を確定するのに使う
  - 探索        … `algorithms/scheduling/*`(Greedy / Backtracking / B&B / CP-SAT)が候補割当を
                   採点するのに使う(`algorithms → domain` の import は許可されている)

**連続勤務日数の判定はここに置かない** ── 事後は `structure._longest_consecutive_run`
(`itertools.pairwise` の 1 回スキャン)、探索は `patterns/sliding_window`(逐次判定)。
`domain` は `algorithms` を import できないためレイヤー上分ける(`Phase-2-2.md` §3.3)。
"""

from __future__ import annotations

from collections.abc import Iterable

from app.domain.problems.shift_scheduler import ShiftData
from app.domain.solutions.shift_scheduler import Assignment

def distinct(ids: Iterable[str]) -> list[str]:
    """同一スロットに同じスタッフが二重登録されていても 1 人と数える(順序は保つ)。"""
    seen: dict[str, None] = {}
    for i in ids:
        seen.setdefault(i, None)
    return list(seen)


def _slot_hours(data: ShiftData) -> dict[str, float]:
    """slot_id -> スロットの長さ(時間)。"""
    return {slot.id: float(slot.end_hour - slot.start_hour) for slot in data.slots}


def hours_by_staff(data: ShiftData, assignments: Assignment) -> dict[str, float]:
    """staff_id -> 週の総勤務時間。0 割当のスタッフも 0.0 で埋める(均等度の母数に入れるため)。"""
    hours = _slot_hours(data)
    out: dict[str, float] = {st.id: 0.0 for st in data.staff}
    for slot_id, staff_ids in assignments.items():
        for sid in distinct(staff_ids):
            out[sid] = out.get(sid, 0.0) + hours.get(slot_id, 0.0)
    return out


def working_days_by_staff(data: ShiftData, assignments: Assignment) -> dict[str, set[str]]:
    """staff_id -> 勤務した ISO 日付の集合。"""
    day_of = {slot.id: slot.day for slot in data.slots}
    out: dict[str, set[str]] = {}
    for slot_id, staff_ids in assignments.items():
        day = day_of.get(slot_id)
        if day is None:
            continue
        for sid in distinct(staff_ids):
            out.setdefault(sid, set()).add(day)
    return out


def labor_cost(data: ShiftData, assignments: Assignment) -> float:
    """Σ(時給 × スロット時間)。README §12.2 の第 1 目的(最小化)。"""
    hours = _slot_hours(data)
    wage = {s.id: s.hourly_wage for s in data.staff}
    total = 0.0
    for slot_id, staff_ids in assignments.items():
        for sid in distinct(staff_ids):
            total += wage.get(sid, 0.0) * hours.get(slot_id, 0.0)
    return total


def day_off_satisfaction(data: ShiftData, assignments: Assignment) -> float:
    """守れた希望休 ÷ 希望休の総数。希望休が無ければ 1.0。README §12.2 の第 2 目的(最大化)。"""
    working = working_days_by_staff(data, assignments)
    requested = kept = 0
    for st in data.staff:
        for day in st.requested_days_off:
            requested += 1
            if day not in working.get(st.id, set()):
                kept += 1
    return 1.0 if requested == 0 else kept / requested


def hour_variance(data: ShiftData, assignments: Assignment) -> float:
    """スタッフごとの週勤務時間の母分散(0 割当のスタッフも含む)。

    勤務時間均等化(README §12.2 の第 3 目的)= これを小さくする。0 割当のスタッフを母数に
    含めることで「一部のスタッフに偏らせる」割当にペナルティがかかる。
    """
    hours = list(hours_by_staff(data, assignments).values())
    if not hours:
        return 0.0
    mean = sum(hours) / len(hours)
    return sum((h - mean) ** 2 for h in hours) / len(hours)


def assignment_metrics(data: ShiftData, assignments: Assignment) -> dict[str, float]:
    """labor_cost / day_off_satisfaction / hour_variance を 1 つの dict に。"""
    return {
        "labor_cost": labor_cost(data, assignments),
        "day_off_satisfaction": day_off_satisfaction(data, assignments),
        "hour_variance": hour_variance(data, assignments),
    }
