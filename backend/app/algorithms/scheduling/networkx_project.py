"""NetworkxCpmStrategy ── networkx の DAG ユーティリティで CPM を組む(オラクル)。

手実装 `CpmScheduleStrategy` の別実装。`meta.name="cpm_nx"`、`implementation="library:networkx"`。
`nx.is_directed_acyclic_graph` / `nx.topological_sort` を使い、前進 / 後退パスの CPM 算術だけ
書く ── 手実装の `topological_sort`(DFS)と `cpm` を**独立に**検算する。`_ops` は積まない。

資源は無視する(cpm と同じ「下界」)── networkx に RCPSP の仕組みは無い。資源つきの最適は
`cp_sat`。このオラクルの役目は「非制約 CPM の makespan / クリティカルパスが手実装と
一致するか」の裏取り(`test_project_strategies.py` の `test_cpm_and_cpm_nx_agree`)。
"""

from __future__ import annotations

import networkx as nx

from app.algorithms.scheduling.critical_path import CpmResult, critical_chain
from app.algorithms.scheduling.project_common import (
    build_durations,
    infeasible_project_solution,
    parse_project_problem,
    project_solution,
)
from app.domain.problems.problem import OptimizationProblem
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution


class NetworkxCpmStrategy:
    """networkx の DAG ユーティリティで CPM を組む(implementation="library:networkx")。"""

    meta = AlgorithmMeta(
        name="cpm_nx",
        family="scheduling",
        implementation="library:networkx",
        time_complexity="O(V + E)",
        space_complexity="O(V + E)",
    )

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data = parse_project_problem(problem)
        dur = build_durations(data)

        graph: nx.DiGraph = nx.DiGraph()
        graph.add_nodes_from(dur)
        graph.add_edges_from((d.predecessor, d.successor) for d in data.dependencies)
        if not nx.is_directed_acyclic_graph(graph):
            return infeasible_project_solution(self.meta)

        order = list(nx.topological_sort(graph))
        successors = {t: list(graph.successors(t)) for t in order}
        # 前進パス: ES[s] = max(EF[t] for t -> s)
        es = dict.fromkeys(order, 0)
        for t in order:
            for s in graph.successors(t):
                es[s] = max(es[s], es[t] + dur[t])
        ef = {t: es[t] + dur[t] for t in order}
        makespan = max(ef.values(), default=0)
        # 後退パス: LF[t] = min(LS[s] for t -> s)、sink は makespan
        lf: dict[str, int] = {}
        ls: dict[str, int] = {}
        for t in reversed(order):
            succ_ls = [ls[s] for s in graph.successors(t)]
            lf[t] = min(succ_ls) if succ_ls else makespan
            ls[t] = lf[t] - dur[t]
        slack = {t: ls[t] - es[t] for t in order}
        critical = {t for t in order if slack[t] == 0}

        result = CpmResult(
            order=order,
            predecessors={t: list(graph.predecessors(t)) for t in order},
            earliest_start=es,
            earliest_finish=ef,
            latest_start=ls,
            latest_finish=lf,
            slack=slack,
            critical_path=critical_chain(order, successors, ef, es, critical),
            makespan=makespan,
            relaxations=0,
        )
        return project_solution(data, dict(es), result, self.meta, ops=None)
