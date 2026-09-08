"""シフト割当ストラテジー共通の足回り。

Greedy / Backtracking / B&B / CP-SAT は「割当の探し方」だけが違う。共通部分をここに集約:
  - `parse_shift_problem`   … ShiftData を取り出す(型チェック)
  - `eligible_staff`        … スロットに入れるスタッフ(可用性 ∧ スキル)。時給昇順
  - `assignment_metrics`    … labor_cost / day_off_satisfaction / hour_variance を計算
  - `on_duty_by_hour`       … 時間帯別の在籍人数(imos 法)。`min_hourly_coverage` の下地
  - `score`                 … objectives の重み付き和スカラー + metrics
  - `respects_hard`         … 完成割当が hard 制約(可用性/スキル/週時間/連続日数/人数)を満たすか
  - `shift_solution`        … 割当 → CandidateSolution

"""

from __future__ import annotations

from app.algorithms.patterns.difference_array import range_add
from app.algorithms.patterns.sliding_window import max_consecutive_days
from app.domain.objectives.weighted_sum import weighted_sum
from app.domain.problems.problem import OptimizationProblem
from app.domain.problems.shift_scheduler import ShiftData, ShiftSlot, Staff
from app.domain.solutions.shift_metrics import (
    assignment_metrics,
    distinct,
    hours_by_staff,
    working_days_by_staff,
)
from app.domain.solutions.shift_scheduler import ShiftSolution
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution
from app.domain.solutions.shift_scheduler import Assignment

def parse_shift_problem(problem: OptimizationProblem) -> ShiftData:
    """ShiftData を取り出す。型が違えば TypeError(select_strategy が守っているはず)。"""
    data = problem.data
    if not isinstance(data, ShiftData):
        raise TypeError(f"expected ShiftData, got {type(data).__name__}")
    return data


def slot_hours(slot: ShiftSlot) -> float:
    """スロットの長さ(時間)。"""
    return float(slot.end_hour - slot.start_hour)


def eligible_staff(slot: ShiftSlot, data: ShiftData) -> list[Staff]:
    """slot に入れるスタッフ(available かつ required_skills を全て持つ)。時給昇順。"""
    need = set(slot.required_skills)
    return sorted(
        (st for st in data.staff if slot.id in st.available_slot_ids and need <= set(st.skills)),
        key=lambda st: (st.hourly_wage, st.id),
    )


# ---------------------------------------------------------------------------
# 時間帯別の在籍人数(imos 法)
# ---------------------------------------------------------------------------


def on_duty_by_hour(data: ShiftData, assignments: Assignment) -> dict[str, list[float]]:
    """day -> 長さ 24 の配列。各時刻に何人が勤務中か(difference_array で O(スロット数))。"""
    slot_by_id = {s.id: s for s in data.slots}
    per_day: dict[str, list[tuple[int, int, float]]] = {}
    for slot_id, staff_ids in assignments.items():
        slot = slot_by_id.get(slot_id)
        if slot is None:
            continue
        headcount = float(len(distinct(staff_ids)))
        per_day.setdefault(slot.day, []).append((slot.start_hour, slot.end_hour, headcount))
    return {day: range_add(24, updates) for day, updates in per_day.items()}


def min_hourly_coverage(data: ShiftData, assignments: Assignment) -> float:
    """スロットが有効な時間帯で、最も人数の少ない時刻の在籍人数。スロットが無ければ inf。"""
    curves = on_duty_by_hour(data, assignments)
    active: dict[str, set[int]] = {}
    for slot in data.slots:
        active.setdefault(slot.day, set()).update(range(slot.start_hour, slot.end_hour))
    worst = float("inf")
    for day, curve in curves.items():
        for hour in active.get(day, ()):
            worst = min(worst, curve[hour])
    return worst


# ---------------------------------------------------------------------------
# hard 制約(完成割当に対する事前フィルタ ── 最終判定は Verification)
# ---------------------------------------------------------------------------


def respects_hard(data: ShiftData, assignments: Assignment) -> bool:
    """完成割当が hard 制約を満たすか(探索の枝刈り用の速い述語)。"""
    slot_by_id = {s.id: s for s in data.slots}
    staff_by_id = {s.id: s for s in data.staff}

    for slot_id, staff_ids in assignments.items():
        slot = slot_by_id.get(slot_id)
        if slot is None:
            return False
        picked = distinct(staff_ids)
        if len(picked) != slot.required_headcount:
            return False
        need = set(slot.required_skills)
        for sid in picked:
            st = staff_by_id.get(sid)
            if st is None or slot.id not in st.available_slot_ids or not need <= set(st.skills):
                return False

    for hours in hours_by_staff(data, assignments).values():
        if hours > data.max_weekly_hours:
            return False

    for days in working_days_by_staff(data, assignments).values():
        if max_consecutive_days(days) > data.max_consecutive_days:
            return False
    return True


# ---------------------------------------------------------------------------
# スコアと解の組み立て
# ---------------------------------------------------------------------------


def score(
    problem: OptimizationProblem, data: ShiftData, assignments: Assignment
) -> tuple[float, dict[str, float]]:
    """(objectives の重み付き和スカラー, metrics)。スカラーは小さいほど良い割当。"""
    metrics = assignment_metrics(data, assignments)
    return weighted_sum(problem.objectives, metrics), metrics


def shift_solution(
    assignments: Assignment | None,
    *,
    data: ShiftData,
    ops: int | None,
    meta: AlgorithmMeta,
    truncated: bool = False,
) -> CandidateSolution:
    """割当(または None = 実行可能解なし)を CandidateSolution に詰める。

    - ops=None(ライブラリトラック)なら "_ops" を入れない
    - truncated=True(B&B が予算切れで打ち切った)なら "_truncated"=1.0
    - status は "valid" or "infeasible"。hard 違反 → "invalid" は Verification が確定する
    """
    ops_metric: dict[str, float] = {} if ops is None else {"_ops": float(ops)}
    trunc_metric = {"_truncated": 1.0} if truncated else {}
    if assignments is None:
        return CandidateSolution(
            status="infeasible",
            assignments=ShiftSolution(assignments={}),
            metrics={**ops_metric, **trunc_metric},
            produced_by=meta,
        )
    return CandidateSolution(
        status="valid",
        assignments=ShiftSolution(assignments=assignments),
        metrics={**assignment_metrics(data, assignments), **ops_metric, **trunc_metric},
        produced_by=meta,
    )