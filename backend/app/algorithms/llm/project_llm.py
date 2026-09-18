"""project_scheduling 用 LLM Only 戦略。設計・失敗時の方針は `route_llm.py` と同じ。"""

from __future__ import annotations

from typing import cast

from app.ai.llm.gemini import get_gemini_llm
from app.algorithms.llm.common import LLM_ONLY_META, render_constraints, render_objectives
from app.domain.problems.problem import OptimizationProblem
from app.domain.problems.project_manager import ProjectData
from app.domain.solutions.project_manager import ProjectSolution
from app.domain.solutions.solution import CandidateSolution


def _prompt(problem: OptimizationProblem, data: ProjectData) -> str:
    """タスク/依存の id カタログ + 資源上限 + 目的 + 制約を自然言語化する。"""
    tasks = "\n".join(
        f"- {t.id}: {t.name or t.id}(所要時間 {t.duration}、資源 {t.resource})" for t in data.tasks
    )
    deps = "\n".join(f"- {d.id}: {d.predecessor} -> {d.successor}" for d in data.dependencies)
    capacity_line = (
        f"資源上限 {data.resource_capacity}\n\n" if data.resource_capacity is not None else ""
    )
    return (
        "次のプロジェクトスケジューリング問題を解いてください。依存関係(先行タスクが終わって"
        "から後続タスクを開始できる)を守り、全タスクの実行順(task_order)と各タスクの"
        "スケジュール(schedule: task_id / start / finish / slack)を決めてください。"
        "クリティカルパス(slack が 0 のタスクを起点から終点まで1本に繋いだ列)と、"
        "全体の所要時間(makespan)も答えてください。\n\n"
        f"タスク:\n{tasks}\n\n依存:\n{deps}\n\n{capacity_line}"
        f"目的:\n{render_objectives(problem)}\n\n制約:\n{render_constraints(problem)}\n\n"
        "finish は start + duration、makespan は全タスクの finish の最大値と矛盾しないよう"
        "正しく計算してください。"
    )


class LlmOnlyProjectStrategy:
    """project_scheduling を LLM に直接解かせる。"""

    meta = LLM_ONLY_META

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data = cast(ProjectData, problem.data)
        llm = get_gemini_llm(temperature=0).with_structured_output(ProjectSolution)
        result = cast(ProjectSolution, llm.invoke(_prompt(problem, data)))
        return CandidateSolution(status="valid", assignments=result, produced_by=self.meta)
