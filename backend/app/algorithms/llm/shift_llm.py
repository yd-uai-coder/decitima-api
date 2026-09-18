"""shift_scheduling 用 LLM Only 戦略。設計・失敗時の方針は `route_llm.py` と同じ。"""

from __future__ import annotations

from typing import cast

from app.ai.llm.gemini import get_gemini_llm
from app.algorithms.llm.common import LLM_ONLY_META, render_constraints, render_objectives
from app.domain.problems.problem import OptimizationProblem
from app.domain.problems.shift_scheduler import ShiftData
from app.domain.solutions.shift_scheduler import ShiftSolution
from app.domain.solutions.solution import CandidateSolution


def _prompt(problem: OptimizationProblem, data: ShiftData) -> str:
    """スタッフ/スロットの id カタログ + 上限 + 目的 + 制約を自然言語化する。"""
    staff = "\n".join(
        f"- {s.id}: 時給{s.hourly_wage}、勤務可能スロット {s.available_slot_ids}、"
        f"スキル {s.skills}、希望休 {s.requested_days_off}"
        for s in data.staff
    )
    slots = "\n".join(
        f"- {sl.id}: {sl.day} {sl.start_hour}-{sl.end_hour}時、"
        f"必要人数 {sl.required_headcount}、必要スキル {sl.required_skills}"
        for sl in data.slots
    )
    return (
        "次のシフト割当問題を解いてください。各スロット id に、そのスロットで勤務可能かつ"
        "必要スキルを満たすスタッフ id を必要人数ぶん割り当ててください"
        "(assignments は {スロットid: [スタッフid, ...]} の形)。\n\n"
        f"スタッフ:\n{staff}\n\nスロット:\n{slots}\n\n"
        f"週労働時間の上限 {data.max_weekly_hours}h、"
        f"連続勤務日数の上限 {data.max_consecutive_days}日\n\n"
        f"目的:\n{render_objectives(problem)}\n\n制約:\n{render_constraints(problem)}"
    )


class LlmOnlyShiftStrategy:
    """shift_scheduling を LLM に直接解かせる。"""

    meta = LLM_ONLY_META

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data = cast(ShiftData, problem.data)
        llm = get_gemini_llm(temperature=0).with_structured_output(ShiftSolution)
        result = cast(ShiftSolution, llm.invoke(_prompt(problem, data)))
        return CandidateSolution(status="valid", assignments=result, produced_by=self.meta)
