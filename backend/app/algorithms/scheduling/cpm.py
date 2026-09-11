"""CpmScheduleStrategy(手実装)── トポロジカルソート + CPM でスケジュールを組む。

**資源 capacity を見ない。** 各タスクを最早開始(ES)に置くだけ ── 「資源が無限にあれば
何日で終わるか」の下界。resource_capacity がきついと、この ES スケジュールは資源を超過し、
Verification(`_verify_project_resources`)が hard 違反で `invalid` にする。

資源を守った feasible な解は `priority_list`(手実装)、厳密な最適は `cp_sat`(OR-Tools)。

`_ops` = CPM の前進 + 後退パスで辺を緩和した回数。
"""

from __future__ import annotations

from app.algorithms.graph.topological import CyclicGraphError
from app.algorithms.scheduling.critical_path import cpm
from app.algorithms.scheduling.project_common import (
    build_durations,
    build_successors,
    infeasible_project_solution,
    parse_project_problem,
    project_solution,
)
from app.domain.problems.problem import OptimizationProblem
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution


class CpmScheduleStrategy:
    """手実装の CPM スケジューラ(implementation="handwritten")。"""

    meta = AlgorithmMeta(
        name="cpm",
        family="scheduling",
        implementation="handwritten",
        time_complexity="O(V + E)",
        space_complexity="O(V)",
    )

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data = parse_project_problem(problem)
        successors = build_successors(data)
        try:
            result = cpm(build_durations(data), successors)
        except CyclicGraphError:
            # 通常は validation が先に弾く。strategy を直接呼ばれたときの保険
            return infeasible_project_solution(self.meta)
        # 資源は見ない ── 各タスクを最早開始(ES)に置く
        starts = dict(result.earliest_start)
        return project_solution(data, starts, result, self.meta, ops=result.relaxations)
