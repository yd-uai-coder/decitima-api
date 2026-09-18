"""logistics_planning 用 LLM Only 戦略。設計・失敗時の方針は `route_llm.py` と同じ。"""

from __future__ import annotations

from typing import cast

from app.ai.llm.gemini import get_gemini_llm
from app.algorithms.llm.common import LLM_ONLY_META, render_constraints, render_objectives
from app.domain.problems.logistics import LogisticsData
from app.domain.problems.problem import OptimizationProblem
from app.domain.solutions.logistics import LogisticsSolution
from app.domain.solutions.solution import CandidateSolution


def _prompt(problem: OptimizationProblem, data: LogisticsData) -> str:
    """デポ/ノード/道路区間/車両/配送先の id カタログ + 目的 + 制約を自然言語化する。"""
    nodes = "\n".join(f"- {n.id}: {n.label or n.id}" for n in data.nodes)
    segments = "\n".join(
        f"- {s.id}: {s.source} <-> {s.target}"
        f"(距離 {s.distance}{'、一方通行(source→target)' if s.directed else ''})"
        for s in data.segments
    )
    vehicles = "\n".join(
        f"- {v.id}: 重量容量 {v.capacity_weight}、体積容量 {v.capacity_volume}"
        for v in data.vehicles
    )
    deliveries = "\n".join(
        f"- {d.id}: ノード {d.node_id}、需要(重量 {d.demand_weight} / 体積 {d.demand_volume})"
        for d in data.deliveries
    )
    return (
        "次の配送計画問題(CVRP)を解いてください。デポ(id=" + data.depot_id + ")から出発し、"
        "各配送先をちょうど1台の車両に(容量を超えない範囲で)割り当て、各車両の訪問順"
        "(stop_ids)を決めてください。使わない車両は routes に含めないでください。\n\n"
        f"ノード:\n{nodes}\n\n道路区間:\n{segments}\n\n車両:\n{vehicles}\n\n配送先:\n{deliveries}\n\n"
        f"目的:\n{render_objectives(problem)}\n\n制約:\n{render_constraints(problem)}\n\n"
        "各 route の distance、および total_distance(全 route の distance 合計)は、"
        "デポ発 → 訪問順 → デポ着の実際の道のりと矛盾しないよう正しく計算してください。"
    )


class LlmOnlyLogisticsStrategy:
    """logistics_planning を LLM に直接解かせる。"""

    meta = LLM_ONLY_META

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data = cast(LogisticsData, problem.data)
        llm = get_gemini_llm(temperature=0).with_structured_output(LogisticsSolution)
        result = cast(LogisticsSolution, llm.invoke(_prompt(problem, data)))
        return CandidateSolution(status="valid", assignments=result, produced_by=self.meta)
