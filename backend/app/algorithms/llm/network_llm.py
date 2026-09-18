# DeciTima samples │ 初出 Phase 14(14-2)
"""network_design 用 LLM Only 戦略。設計・失敗時の方針は `route_llm.py` と同じ"""

from __future__ import annotations

from typing import cast
from pydantic import BaseModel

from app.ai.llm.gemini import get_gemini_llm
from app.algorithms.llm.common import (
    LLM_ONLY_META,
    render_constraints,
    render_objectives,
    strip_problem_type,
)
from app.domain.problems.network_design import NetworkDesignData
from app.domain.problems.problem import OptimizationProblem
from app.domain.solutions.network_design import NetworkDesignSolution
from app.domain.solutions.solution import CandidateSolution


def _prompt(problem: OptimizationProblem, data: NetworkDesignData) -> str:
    """拠点/リンクの id カタログ + 目的 + 制約を自然言語化する。"""
    nodes = "\n".join(f"- {n.id}: {n.label or n.id}" for n in data.nodes)
    links = "\n".join(
        f"- {link.id}: {link.endpoints[0]} - {link.endpoints[1]}(コスト {link.weight})"
        for link in data.links
    )
    return (
        "次のネットワーク設計問題(最小全域木)を解いてください。下記に実在するリンク id"
        "だけを使い、全ての拠点を1つの木で(閉路を作らずに)接続するリンクの集合を選んで"
        "ください。\n\n"
        f"拠点:\n{nodes}\n\nリンク候補:\n{links}\n\n"
        f"目的:\n{render_objectives(problem)}\n\n制約:\n{render_constraints(problem)}\n\n"
        "total_weight は実際に選んだリンクのコスト合計と矛盾しないよう正しく計算してください。"
    )


class LlmOnlyNetworkStrategy:
    """network_design を LLM に直接解かせる。"""

    meta = LLM_ONLY_META

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data = cast(NetworkDesignData, problem.data)
        # strip_problem_type: 判別子は LLM に見せない(common.py 冒頭の解説を参照)
        llm = get_gemini_llm(temperature=0).with_structured_output(
            strip_problem_type(NetworkDesignSolution)
        )
        raw = cast(BaseModel, llm.invoke(_prompt(problem, data)))
        result = NetworkDesignSolution(
            problem_type="network_design", **raw.model_dump(exclude={"problem_type"})
        )
        return CandidateSolution(status="valid", assignments=result, produced_by=self.meta)
