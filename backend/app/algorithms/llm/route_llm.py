"""route_planning 用 LLM Only 戦略。

`AlgorithmStrategy` Protocol に準拠するが `REGISTRY` には登録しない ── `ComparisonService`
が比較専用に直接インスタンス化する。出力スキーマは既存 `RouteSolution` をそのまま
`with_structured_output()` に渡す(変換コード無しで既存 `SolutionVerificationService` に
そのまま通せる)。

Structuring/Recommendation/Explanation と異なり、失敗時のリトライ・グレースフルデグレードは
**しない**。「生の」LLM 信頼性を測ることが目的なので、例外はそのまま
`ComparisonService` に伝播させ「エラー率」の分子として数える。
"""

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
from app.domain.problems.problem import OptimizationProblem
from app.domain.problems.route_planner import RouteData
from app.domain.solutions.route_planner import RouteSolution
from app.domain.solutions.solution import CandidateSolution


def _prompt(problem: OptimizationProblem, data: RouteData) -> str:
    """ノード/エッジの id カタログ + start/goal + 目的 + 制約を自然言語化する。"""
    nodes = "\n".join(f"- {n.id}: {n.label or n.id}" for n in data.nodes)
    edges = "\n".join(
        f"- {e.id}: {e.source} <-> {e.target}"
        f"(重み {e.weight}{'、一方通行(source→target)' if e.directed else ''})"
        for e in data.edges
    )
    return (
        "次の経路探索問題を解いてください。start から goal まで、下記に実在するノード id・"
        "エッジ id だけを使って経路を1つ構築してください。\n\n"
        f"ノード:\n{nodes}\n\nエッジ:\n{edges}\n\n"
        f"start={data.start} / goal={data.goal}\n\n"
        f"目的:\n{render_objectives(problem)}\n\n制約:\n{render_constraints(problem)}\n\n"
        "total_weight は実際に選んだエッジの重みの合計と矛盾しないよう正しく計算してください。"
    )


class LlmOnlyRouteStrategy:
    """route_planning を LLM に直接解かせる(README §14 の「LLM Only」経路)。"""

    meta = LLM_ONLY_META

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data = cast(RouteData, problem.data)
        # strip_problem_type: 判別子は LLM に見せない(Gemini の構造化出力は Literal の
        # 単一値制約(JSON Schema の const)を保証しないため。common.py 冒頭の解説を参照
        llm = get_gemini_llm(temperature=0).with_structured_output(
            strip_problem_type(RouteSolution)
        )
        # invoke: 同期呼び出し(ComparisonService が asyncio.to_thread の中で呼ぶ前提)
        # cast: with_structured_output().invoke() の戻り型は dict | BaseModel にしか
        # narrowing されない(Phase 11 の既知の型債務と同じ理由)
        raw = cast(BaseModel, llm.invoke(_prompt(problem, data)))
        result = RouteSolution(
            problem_type="route_planning", **raw.model_dump(exclude={"problem_type"})
        )
        return CandidateSolution(status="valid", assignments=result, produced_by=self.meta)
