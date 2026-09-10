"""SolutionVerificationService ── 解の制約充足(候補解が出た後)。

- 解の型ごとの「構造検証」は app/domain/solutions/structure.py
  (verify_route_structure / verify_shift_structure)。shift はここで
  labor_cost / day_off_satisfaction の metrics も確定する。
- 制約 kind ごとのチェッカーは app/domain/constraints/(CHECKERS レジストリ)。
"""

from __future__ import annotations

from app.algorithms.graph.connectivity import forms_spanning_tree
from app.algorithms.optimization.travel_common import all_pairs, tour_cost
from app.domain.constraints import CHECKERS
from app.domain.problems.network_design import NetworkDesignData
from app.domain.problems.problem import OptimizationProblem
from app.domain.problems.travel_planner import TravelData
from app.domain.solutions.solution import CandidateSolution, ConstraintViolation
from app.domain.solutions.network_design import NetworkDesignSolution
from app.domain.solutions.structure import structural_verify
from app.domain.solutions.travel_planner import TravelSolution

class SolutionVerificationService:
    """候補解が problem のすべての制約を満たすか検証し、status と violations を確定する。"""

    def verify(
        self, problem: OptimizationProblem, solution: CandidateSolution
    ) -> CandidateSolution:
        if solution.status == "infeasible":
            return solution  # 解が無いものは検証しない

        # 1. 構造検証。解の型ごとに常に必要な検査 + 追加メトリクス(shift の labor_cost 等)
        structural, extra_metrics = structural_verify(problem, solution)
        structural = [
            *structural,
            *_verify_spanning_tree(problem, solution),
            *_verify_travel_plan(problem, solution), 
            ]
        enriched = solution.model_copy(update={"metrics": {**solution.metrics, **extra_metrics}})

        # 2. 制約 kind ごとのチェッカー。enriched の metrics(構造検証後)を読む
        kind_violations: list[ConstraintViolation] = []
        # 制約 kind ごとにディスパッチ
        for c in problem.constraints:
            checker = CHECKERS.get(c.kind)
            if checker is None:
                continue  # 未対応 kind は素通し(Phase 2 で埋める)
            v = checker(c, problem, enriched)
            if v is not None:
                kind_violations.append(v)

        violations = [*structural, *kind_violations]
        has_hard = any(v.severity == "hard" for v in violations)

        return enriched.model_copy(
            update={
                "status": "invalid" if has_hard else enriched.status,
                "violations": violations,
                "metrics": {**enriched.metrics, "soft_penalty": _soft_penalty(problem, violations)},
            }
        )


def _verify_spanning_tree(
    problem: OptimizationProblem, solution: CandidateSolution
) -> list[ConstraintViolation]:
    """network_design 解: 選んだリンクが全拠点を繋ぐ木になっているか。"""
    if not (
        isinstance(problem.data, NetworkDesignData)
        and isinstance(solution.assignments, NetworkDesignSolution)
    ):
        return []
    link_by_id = {link.id: link for link in problem.data.links}
    pairs = [
        link_by_id[lid].endpoints
        for lid in solution.assignments.selected_link_ids
        if lid in link_by_id
    ]
    node_ids = [n.id for n in problem.data.nodes]
    if forms_spanning_tree(node_ids, pairs):
        return []
    return [
        ConstraintViolation(
            constraint_kind="network_structure",
            severity="hard",
            message="selected links do not form a spanning tree (connect all nodes, no cycle)",
        )
    ]


def _verify_travel_plan(
    problem: OptimizationProblem, solution: CandidateSolution
) -> list[ConstraintViolation]:
    """travel_planning 解: 申告した total_cost / total_time が実際の巡回コストと合うか。

    Floyd-Warshall で全点対距離を出し直し、solution.visit_order の順(再最適化しない)で
    place + 移動のコストを積んで比べる。合わなければ strategy が嘘をついている(hard)。
    """
    if not (
        isinstance(problem.data, TravelData) and isinstance(solution.assignments, TravelSolution)
    ):
        return []
    cost_dist, time_dist = all_pairs(problem.data)
    real_cost, real_time = tour_cost(
        problem.data, solution.assignments.visit_order, cost_dist, time_dist
    )
    out: list[ConstraintViolation] = []
    if abs(real_cost - solution.assignments.total_cost) > 1e-6:
        out.append(
            ConstraintViolation(
                constraint_kind="travel_structure",
                severity="hard",
                message=f"claimed total_cost {solution.assignments.total_cost} "
                f"!= recomputed {real_cost}",
            )
        )
    if abs(real_time - solution.assignments.total_time) > 1e-6:
        out.append(
            ConstraintViolation(
                constraint_kind="travel_structure",
                severity="hard",
                message=f"claimed total_time {solution.assignments.total_time} "
                f"!= recomputed {real_time}",
            )
        )
    return out


def _soft_penalty(problem: OptimizationProblem, violations: list[ConstraintViolation]) -> float:
    """違反した soft 制約の penalty 合計。Phase 1 は kind 一致で素朴に対応付ける"""
    violated_kinds = {v.constraint_kind for v in violations if v.severity == "soft"}
    return sum(
        (c.penalty or 0.0)
        for c in problem.constraints
        if c.severity == "soft" and c.kind in violated_kinds
    )
