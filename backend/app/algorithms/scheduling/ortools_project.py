"""OrToolsCpSatProjectStrategy(産業ソルバートラック)── CP-SAT で RCPSP を厳密に解く。

手実装(cpm / priority_list)と**同じ `AlgorithmStrategy` 契約・同じ `ProjectSolution`**。
違うのは `implementation="library:ortools"` と、中身が CP-SAT の探索であること。仕事がソルバーの
中なので `_ops` は出さない(2 トラック比較の観察点。)。

RCPSP(resource-constrained project scheduling)は NP 困難。priority_list の貪欲は feasible だが
最適とは限らない ── CP-SAT は cumulative 制約つきで makespan 最小を厳密に求める(fixture では
priority_list=10 に対し cp_sat=9)。「手実装ヒューリスティックが最適を外す → 産業ソルバー」

モデル:
  - タスクごと interval var(start / duration / end)
  - 依存: `start[successor] >= end[predecessor]`
  - 資源: `add_cumulative(intervals, demands, resource_capacity)`(同時実行の需要合計 ≤ 容量)
  - 目的: `minimize(max(end))`

**決定論**: `num_search_workers=1` + `random_seed` 固定。

slack / critical_path / task_order は手実装 `cpm`(資源無視)から供給 ── これらは「資源が
無ければどこが律速か」の構造的な情報。CP-SAT が返すのは実際の開始時刻だけ。
"""

from __future__ import annotations

from ortools.sat.python import cp_model

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


class OrToolsCpSatProjectStrategy:
    """OR-Tools CP-SAT で RCPSP を解く(implementation="library:ortools")。"""

    meta = AlgorithmMeta(
        name="cp_sat",
        family="scheduling",
        implementation="library:ortools",
        time_complexity="理論的には NP 困難(RCPSP)、実用上は多くの規模で現実的",
        space_complexity="ソルバー依存",
    )

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data = parse_project_problem(problem)
        successors = build_successors(data)
        dur = build_durations(data)
        try:
            structure = cpm(dur, successors)
        except CyclicGraphError:
            return infeasible_project_solution(self.meta)

        horizon = sum(dur.values())  # 全タスク直列 = 開始時刻の上界
        model = cp_model.CpModel()
        starts = {t.id: model.new_int_var(0, horizon, f"s_{t.id}") for t in data.tasks}
        ends = {t.id: model.new_int_var(0, horizon, f"e_{t.id}") for t in data.tasks}
        intervals = {
            t.id: model.new_interval_var(starts[t.id], dur[t.id], ends[t.id], f"iv_{t.id}")
            for t in data.tasks
        }

        for d in data.dependencies:
            model.add(starts[d.successor] >= ends[d.predecessor])

        if data.resource_capacity is not None:
            demands = [t.resource for t in data.tasks]
            if any(demands):
                model.add_cumulative(
                    [intervals[t.id] for t in data.tasks], demands, data.resource_capacity
                )

        makespan = model.new_int_var(0, horizon, "makespan")
        model.add_max_equality(makespan, list(ends.values()))
        model.minimize(makespan)

        solver = cp_model.CpSolver()
        solver.parameters.num_search_workers = 1
        solver.parameters.random_seed = 0
        status = solver.solve(model)
        if status not in (cp_model.OPTIMAL, cp_model.FEASIBLE):
            return infeasible_project_solution(self.meta)

        actual = {t.id: int(solver.value(starts[t.id])) for t in data.tasks}
        return project_solution(data, actual, structure, self.meta, ops=None)
