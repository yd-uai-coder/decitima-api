"""GreedyShiftStrategy(貪欲法)── スロットを「厳しい順」に見て、最も安い入れられるスタッフを取る。

貪欲は最適を保証しない ── 埋まらないスロットが残ることも、目的値が最善でないこともある。
その場合でも例外は投げず `status="valid"` の候補を返し、hard 違反の判定は Verification に任せる
(`Phase-0-6.md` ── 「近似アルゴリズムの制約違反はバグでなく invalid な候補」)。

`_ops` = 割当を試みた回数。
"""

from __future__ import annotations

from app.algorithms.patterns.sliding_window import run_length_at, to_ordinal
from app.algorithms.scheduling.common import (
    Assignment,
    eligible_staff,
    parse_shift_problem,
    shift_solution,
    slot_hours,
)
from app.domain.problems.problem import OptimizationProblem
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution


class GreedyShiftStrategy:
    """手実装の貪欲法(implementation="handwritten")。"""

    meta = AlgorithmMeta(
        name="greedy",
        family="scheduling",
        implementation="handwritten",
        time_complexity="O(スロット数 × スタッフ数 log スタッフ数)",
        space_complexity="O(スタッフ数 + スロット数)",
    )

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data = parse_shift_problem(problem)
        assignments: Assignment = {}
        ops = 0

        # 週勤務時間と勤務日(序数集合)を逐次追跡
        hours: dict[str, float] = {st.id: 0.0 for st in data.staff}
        days: dict[str, set[int]] = {st.id: set() for st in data.staff}

        # スロットを「入れられるスタッフが少ない順」= 厳しい順に処理
        order = sorted(data.slots, key=lambda s: (len(eligible_staff(s, data)), s.id))
        for slot in order:
            picked: list[str] = []
            length = slot_hours(slot)
            day_ord = to_ordinal(slot.day)
            for st in eligible_staff(slot, data):
                if len(picked) == slot.required_headcount:
                    break
                ops += 1
                if st.id in picked:
                    continue
                if hours[st.id] + length > data.max_weekly_hours:
                    continue  # 週勤務時間オーバー
                trial = days[st.id] | {day_ord}
                if run_length_at(trial, day_ord) > data.max_consecutive_days:
                    continue  # 連続勤務日数オーバー
                picked.append(st.id)
                hours[st.id] += length
                days[st.id] = trial
            assignments[slot.id] = picked  # 埋まらなくてもそのまま(Verification が invalid にする)

        return shift_solution(assignments, data=data, ops=ops, meta=self.meta)
