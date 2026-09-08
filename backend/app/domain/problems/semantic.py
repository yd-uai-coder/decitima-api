"""Semantic Validation ── 問題全体を見ないと分からない整合・実行可能性の検査。"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from app.domain.problems.problem import OptimizationProblem
from app.domain.problems.route_planner import RouteData
from app.domain.problems.shift_scheduler import ShiftData
from app.domain.problems.network_design import NetworkDesignData


@dataclass(frozen=True)
class SemanticIssue:
    """Semantic Validation が見つけた問題1件。"""

    message: str
    infeasible: bool = False  # True なら「原理的に解なし」


# 検査関数の共通シグネチャ
type SemanticCheck = Callable[[OptimizationProblem], list[SemanticIssue]]


# ---------------------------------------------------------------------------
# route_planning
# ---------------------------------------------------------------------------


def check_route_endpoints(problem: OptimizationProblem) -> list[SemanticIssue]:
    """start / goal が nodes に実在するか。"""
    if not isinstance(problem.data, RouteData):
        return []
    node_ids = {n.id for n in problem.data.nodes}
    issues: list[SemanticIssue] = []
    if problem.data.start not in node_ids:
        issues.append(SemanticIssue(f"start node {problem.data.start!r} not found in nodes"))
    if problem.data.goal not in node_ids:
        issues.append(SemanticIssue(f"goal node {problem.data.goal!r} not found in nodes"))
    return issues


def check_route_edge_endpoints(problem: OptimizationProblem) -> list[SemanticIssue]:
    """各エッジの source / target が nodes に実在するか。"""
    if not isinstance(problem.data, RouteData):
        return []
    node_ids = {n.id for n in problem.data.nodes}
    return [
        SemanticIssue(f"edge {edge.id!r} references unknown node {endpoint!r}")
        for edge in problem.data.edges
        for endpoint in (edge.source, edge.target)
        if endpoint not in node_ids
    ]


# ---------------------------------------------------------------------------
# shift_scheduling
# ---------------------------------------------------------------------------


def check_shift_slot_refs(problem: OptimizationProblem) -> list[SemanticIssue]:
    """スタッフの available_slot_ids / requested 系が実在スロットを指すか。"""
    if not isinstance(problem.data, ShiftData):
        return []
    slot_ids = {s.id for s in problem.data.slots}
    return [
        SemanticIssue(f"staff {staff.id!r} references unknown slot {sid!r}")
        for staff in problem.data.staff
        for sid in staff.available_slot_ids
        if sid not in slot_ids
    ]


def check_shift_staffing_feasible(problem: OptimizationProblem) -> list[SemanticIssue]:
    """各スロットに『入れる』スタッフ数が required_headcount 以上いるか(いなければ infeasible)。"""
    if not isinstance(problem.data, ShiftData):
        return []
    issues: list[SemanticIssue] = []
    for slot in problem.data.slots:
        eligible = [
            st
            for st in problem.data.staff
            if slot.id in st.available_slot_ids and set(slot.required_skills) <= set(st.skills)
        ]
        if len(eligible) < slot.required_headcount:
            issues.append(
                SemanticIssue(
                    f"slot {slot.id!r} needs {slot.required_headcount} staff "
                    f"but only {len(eligible)} are eligible",
                    infeasible=True,
                )
            )
    return issues


def check_shift_skill_coverage(problem: OptimizationProblem) -> list[SemanticIssue]:
    """スロットの required_skills を持ち、かつそのスロットに入れるスタッフが存在するか。"""
    if not isinstance(problem.data, ShiftData):
        return []
    issues: list[SemanticIssue] = []
    for slot in problem.data.slots:
        for skill in slot.required_skills:
            holders = [
                st
                for st in problem.data.staff
                if skill in st.skills and slot.id in st.available_slot_ids
            ]
            if not holders:
                issues.append(
                    SemanticIssue(
                        f"slot {slot.id!r} requires skill {skill!r} but no available staff has it",
                        infeasible=True,
                    )
                )
    return issues


def check_shift_weekly_hours_cover(problem: OptimizationProblem) -> list[SemanticIssue]:
    """max_weekly_hours が最低でも1スロット分の長さを許容するか(でなければ全スロット不成立)。"""
    if not isinstance(problem.data, ShiftData):
        return []
    if not problem.data.slots:
        return []
    longest = max(slot.end_hour - slot.start_hour for slot in problem.data.slots)
    if longest > problem.data.max_weekly_hours:
        return [
            SemanticIssue(
                f"max_weekly_hours {problem.data.max_weekly_hours} is shorter than "
                f"the longest slot ({longest}h): no staff can cover it",
                infeasible=True,
            )
        ]
    return []

# ---------------------------------------------------------------------------
# network_design
# ---------------------------------------------------------------------------

def check_network_link_endpoints(problem: OptimizationProblem) -> list[SemanticIssue]:
    """各リンクの endpoints が nodes に実在するか。"""
    if not isinstance(problem.data, NetworkDesignData):
        return []
    node_ids = {n.id for n in problem.data.nodes}
    return [
        SemanticIssue(f"link {link.id!r} references unknown node {endpoint!r}")
        for link in problem.data.links
        for endpoint in link.endpoints
        if endpoint not in node_ids
    ]


def check_network_has_links(problem: OptimizationProblem) -> list[SemanticIssue]:
    """拠点が2つ以上あるのに敷設可能リンクが空なら、全域木は作れない(infeasible)。"""
    if not isinstance(problem.data, NetworkDesignData):
        return []
    if len(problem.data.nodes) >= 2 and not problem.data.links:
        return [
            SemanticIssue("network_design has >= 2 nodes but no candidate links", infeasible=True)
        ]
    return []


# ---------------------------------------------------------------------------
# レジストリ ── problem_type ごとの検査リスト。新しい problem_type はここに 1 エントリ足す
# ---------------------------------------------------------------------------

SEMANTIC_CHECKS: dict[str, list[SemanticCheck]] = {
    "route_planning": [
        check_route_endpoints,
        check_route_edge_endpoints,
    ],
    "shift_scheduling": [
        check_shift_slot_refs,
        check_shift_staffing_feasible,
        check_shift_skill_coverage,
        check_shift_weekly_hours_cover,
    ],
    "network_design":[
        check_network_link_endpoints,
        check_network_has_links,
    ],
}
