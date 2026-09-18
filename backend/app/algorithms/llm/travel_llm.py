"""travel_planning 用 LLM Only 戦略。設計・失敗時の方針は `route_llm.py` と同じ。"""

from __future__ import annotations

from typing import cast
from pydantic import BaseModel

from app.ai.llm.gemini import get_gemini_llm
from app.domain.problems.problem import OptimizationProblem
from app.algorithms.llm.common import (
    LLM_ONLY_META,
    render_constraints,
    render_objectives,
    strip_problem_type,
)
from app.domain.problems.travel_planner import TravelData
from app.domain.solutions.solution import CandidateSolution
from app.domain.solutions.travel_planner import TravelSolution


def _prompt(problem: OptimizationProblem, data: TravelData) -> str:
    """place/leg の id カタログ + 予算 + 目的 + 制約を自然言語化する。"""
    places = "\n".join(
        f"- {p.id}: {p.name or p.id}(価値 {p.value}、費用 {p.cost}、所要時間 {p.duration}、"
        f"好み係数 {data.preferences.get(p.id, 1.0)})"
        for p in data.places
    )
    legs = "\n".join(
        f"- {leg.id}: {leg.endpoints[0]} <-> {leg.endpoints[1]}"
        f"(移動費用 {leg.travel_cost}、移動時間 {leg.travel_time})"
        for leg in data.legs
    )
    start_line = f"、起点 {data.start}" if data.start else ""
    return (
        "次の旅行プラン問題を解いてください。予算・時間予算の範囲内で、好み加重の価値の合計"
        "(total_value)が最大になるよう訪問する place を選び(selected_place_ids)、その"
        f"巡回順(visit_order)を決めてください{start_line}。\n\n"
        f"訪問候補:\n{places}\n\n移動区間:\n{legs}\n\n"
        f"予算 {data.budget}、時間予算 {data.time_budget}\n\n"
        f"目的:\n{render_objectives(problem)}\n\n制約:\n{render_constraints(problem)}\n\n"
        "total_value / total_cost / total_time は実際に選んだ内容・移動と矛盾しないよう"
        "正しく計算してください。"
    )


class LlmOnlyTravelStrategy:
    """travel_planning を LLM に直接解かせる。"""

    meta = LLM_ONLY_META

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data = cast(TravelData, problem.data)
        # strip_problem_type: 判別子は LLM に見せない(common.py 冒頭の解説を参照)
        llm = get_gemini_llm(temperature=0).with_structured_output(
            strip_problem_type(TravelSolution)
        )
        raw = cast(BaseModel, llm.invoke(_prompt(problem, data)))
        result = TravelSolution(
            problem_type="travel_planning", **raw.model_dump(exclude={"problem_type"})
        )
        return CandidateSolution(status="valid", assignments=result, produced_by=self.meta)
