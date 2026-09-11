"""PriorityListScheduleStrategy(手実装)── 資源制約つきスケジューリングの貪欲法。

serial SGS(schedule generation scheme): CPM で余裕(slack)を出し、**余裕の少ないタスクから**
(= 最遅開始 LS の昇順)1 本ずつ、
  - 全先行タスクが終わった時刻以降で
  - その区間に demand を足しても資源使用量が capacity を超えない
最早の時刻に置いていく。

常に資源 feasible。ただし貪欲なので makespan は最適とは限らない ── 早く置いたタスクが
後続タスクの置き場を塞ぐ(fixture では priority_list=10 に対し cp_sat=9)。
「手実装ヒューリスティックが最適を外す → 産業ソルバー(cp_sat)

`resource_capacity is None` なら資源チェックが空回りして cpm と同じ ES スケジュールになる。
`_ops` = 開始時刻をずらして資源をプローブした回数。
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


class PriorityListScheduleStrategy:
    """資源制約つき貪欲スケジューラ(implementation="handwritten")。"""

    meta = AlgorithmMeta(
        name="priority_list",
        family="scheduling",
        implementation="handwritten",
        time_complexity="O(V · H + E)  (H = スケジュール地平)",
        space_complexity="O(V + H)",
    )

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data = parse_project_problem(problem)
        successors = build_successors(data)
        dur = build_durations(data)
        try:
            result = cpm(dur, successors)
        except CyclicGraphError:
            return infeasible_project_solution(self.meta)

        demand = {t.id: t.resource for t in data.tasks}
        cap = data.resource_capacity

        # 優先順位 = 最遅開始(LS)の昇順 = 余裕の少ないタスクから。同点は id 昇順で決定論
        priority = sorted(result.order, key=lambda t: (result.latest_start[t], t))

        starts: dict[str, int] = {}
        usage: dict[int, int] = {}  # 時刻 -> 資源使用量(可変長プロファイル)
        ops = 0
        for t in priority:
            # predecessors：先行 task 群(tの隣接タスク)
        
            ready = max((starts[p] + dur[p] for p in result.predecessors[t]), default=0)
            start = ready
            if cap is not None and demand[t] > 0:
                # demand を足しても capacity を超えない最早の start を探す
                while not all(
                    usage.get(x, 0) + demand[t] <= cap for x in range(start, start + dur[t])
                ):
                    ops += 1
                    start += 1
            starts[t] = start
            for x in range(start, start + dur[t]):
                usage[x] = usage.get(x, 0) + demand[t]

        return project_solution(data, starts, result, self.meta, ops=ops)
