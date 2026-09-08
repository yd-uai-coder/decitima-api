"""解の「構造検証」── 制約 kind に紐づかない、解の型ごとに常に成り立つべき検査。

- verify_route_structure … 経路が連結 / 始終点 / total_weight 整合(すべて hard)
- verify_shift_structure … 割当が実在 id / 可用性 / 必要スキル / 週勤務時間 / 連続勤務日数(hard)、
  希望休(soft)、labor_cost・day_off_satisfaction(metrics)

このモジュールは葉(route_planner.py / shift_scheduler.py)とアグリゲータ(solution.py)を
import するが、それらはこのモジュールを import しない(一方向)。

**純粋述語だけ**を置く。「選んだリンクが実際に全域木を成すか(連結 ∧ 非閉路)」は BFS を走らせる
計算なので、ここではなく SolutionVerificationService が `connectivity.forms_spanning_tree` で
判定する(route の到達可能性を validation.py に置くのと同じ切り分け。`Phase-2-2.md` §3)。
"""

from __future__ import annotations

from datetime import date
from itertools import pairwise

from app.domain.problems.network_design import NetworkDesignData
from app.domain.problems.problem import OptimizationProblem
from app.domain.problems.route_planner import RouteData
from app.domain.problems.shift_scheduler import ShiftData
from app.domain.solutions.network_design import NetworkDesignSolution
from app.domain.solutions.route_planner import RouteSolution
from app.domain.solutions.shift_metrics import (
    assignment_metrics,
    distinct,
    hours_by_staff,
    working_days_by_staff,
)
from app.domain.solutions.shift_scheduler import ShiftSolution
from app.domain.solutions.solution import CandidateSolution, ConstraintViolation


def structural_verify(
    problem: OptimizationProblem, solution: CandidateSolution
) -> tuple[list[ConstraintViolation], dict[str, float]]:
    """解の型を見て対応する構造検証にディスパッチ。(違反リスト, 追加メトリクス) を返す。"""
    assignments = solution.assignments
    if isinstance(assignments, RouteSolution) and isinstance(problem.data, RouteData):
        return verify_route_structure(problem.data, assignments), {}
    if isinstance(assignments, ShiftSolution) and isinstance(problem.data, ShiftData):
        return verify_shift_structure(problem.data, assignments)
    return [], {}


# ---------------------------------------------------------------------------
# route
# ---------------------------------------------------------------------------


def verify_route_structure(data: RouteData, sol: RouteSolution) -> list[ConstraintViolation]:
    """経路が連結・始終点・weight 整合を満たすか。すべて hard。"""
    out: list[ConstraintViolation] = []
    edge_by_id = {e.id: e for e in data.edges}

    if not sol.path_node_ids or sol.path_node_ids[0] != data.start:
        out.append(_hard("route_structure", f"path does not start at {data.start!r}"))
    if not sol.path_node_ids or sol.path_node_ids[-1] != data.goal:
        out.append(_hard("route_structure", f"path does not end at {data.goal!r}"))

    if len(sol.path_edge_ids) != max(len(sol.path_node_ids) - 1, 0):
        out.append(_hard("route_structure", "path_edge_ids length != path_node_ids length - 1"))
        return out  # 以降の照合が成り立たないので打ち切り

    total = 0.0
    for i, edge_id in enumerate(sol.path_edge_ids):
        edge = edge_by_id.get(edge_id)
        a, b = sol.path_node_ids[i], sol.path_node_ids[i + 1]
        if edge is None:
            out.append(_hard("route_structure", f"unknown edge {edge_id!r} in path"))
            continue
        endpoints = {edge.source, edge.target}
        directed_ok = edge.directed and (edge.source, edge.target) == (a, b)
        if endpoints != {a, b} and not directed_ok:
            out.append(_hard("route_structure", f"edge {edge_id!r} does not connect {a!r}-{b!r}"))
        total += edge.weight

    if abs(total - sol.total_weight) > 1e-9:
        out.append(_hard("route_structure", f"total_weight {sol.total_weight} != edge sum {total}"))
    return out


# ---------------------------------------------------------------------------
# shift
# ---------------------------------------------------------------------------


def verify_shift_structure(
    data: ShiftData, sol: ShiftSolution
) -> tuple[list[ConstraintViolation], dict[str, float]]:
    """シフト解の構造を検証し、labor_cost / day_off_satisfaction を計算する。"""
    out: list[ConstraintViolation] = []
    slot_by_id = {s.id: s for s in data.slots}
    staff_by_id = {s.id: s for s in data.staff}

    assignments = sol.assignments

    # 1. 割当が実在する slot / staff を指すか
    for slot_id, staff_ids in assignments.items():
        if slot_id not in slot_by_id:
            out.append(_hard("shift_structure", f"assignment references unknown slot {slot_id!r}"))
        for sid in staff_ids:
            if sid not in staff_by_id:
                out.append(
                    _hard(
                        "shift_structure", 
                        f"assignment references unknown staff {sid!r}"
                    )
                )

    # 2. 割当スタッフはそのスロットを available に持つ + 必要スキルを満たす
    for slot in data.slots:
        for sid in distinct(assignments.get(slot.id, [])):
            staff = staff_by_id.get(sid)
            if staff is None:
                continue
            if slot.id not in staff.available_slot_ids:
                out.append(
                    _hard(
                        "shift_structure", f"staff {sid!r} assigned to unavailable slot {slot.id!r}"
                    )
                )
            missing = set(slot.required_skills) - set(staff.skills)
            if missing:
                out.append(
                    _hard(
                        "shift_structure",
                        f"staff {sid!r} lacks skill(s) {sorted(missing)} for slot {slot.id!r}",
                    )
                )

    # 3. 週勤務時間 <= max_weekly_hours
    for sid, hours in hours_by_staff(data, assignments).items():
        if hours > data.max_weekly_hours:
            out.append(
                _hard(
                    "shift_structure",
                    f"staff {sid!r} works {hours}h > max_weekly_hours {data.max_weekly_hours}",
                )
            )

    # 4. 連続勤務日数 <= max_consecutive_days(素の日次スキャン ── Sliding Window は使わない)
    working_days = working_days_by_staff(data, assignments)
    for sid, days in working_days.items():
        run = _longest_consecutive_run(days)
        if run > data.max_consecutive_days:
            out.append(
                _hard(
                    "shift_structure",
                    f"staff {sid!r} works {run} consecutive days > max {data.max_consecutive_days}",
                )
            )

    # 5. soft: 希望休にあたる日に割り当てられた
    for sid, days in working_days.items():
        staff = staff_by_id.get(sid)
        if staff is None:
            continue
        hit = sorted(set(staff.requested_days_off) & days)
        if hit:
            out.append(
                ConstraintViolation(
                    constraint_kind="respect_days_off",
                    severity="soft",
                    message=f"staff {sid!r} assigned on requested day(s) off: {hit}",
                    detail={"staff": sid, "days": hit},
                )
            )

    # metrics は shift_metrics.py を呼ぶだけ ── 探索(algorithms/scheduling)と同じコードなので
    # 検証で報告する値と探索がスコアリングに使う値がズレない(Phase 6-1)。
    return out, assignment_metrics(data, assignments)

# ---------------------------------------------------------------------------
# network_design
# ---------------------------------------------------------------------------


def verify_network_structure(
    data: NetworkDesignData, sol: NetworkDesignSolution
) -> list[ConstraintViolation]:
    """選択リンクが全域木の「形」を満たすか(純粋述語のみ。連結 ∧ 非閉路は service が判定)。"""
    out: list[ConstraintViolation] = []
    link_by_id = {link.id: link for link in data.links}
    node_ids = {n.id for n in data.nodes}

    unknown = [lid for lid in sol.selected_link_ids if lid not in link_by_id]
    for lid in unknown:
        out.append(_hard("network_structure", f"unknown link {lid!r} in solution"))

    known = [link_by_id[lid] for lid in sol.selected_link_ids if lid in link_by_id]

    expected = max(len(node_ids) - 1, 0)
    if len(sol.selected_link_ids) != expected:
        out.append(
            _hard(
                "network_structure",
                f"spanning tree needs {expected} link(s), got {len(sol.selected_link_ids)}",
            )
        )

    for link in known:
        for endpoint in link.endpoints:
            if endpoint not in node_ids:
                out.append(
                    _hard(
                        "network_structure",
                        f"link {link.id!r} touches unknown node {endpoint!r}",
                    )
                )

    total = sum(link.weight for link in known)
    if abs(total - sol.total_weight) > 1e-9:
        out.append(
            _hard(
                "network_structure",
                f"total_weight {sol.total_weight} != link sum {total}",
            )
        )
    return out

# ---------------------------------------------------------------------------
# 補助
# ---------------------------------------------------------------------------


def _hard(kind: str, message: str) -> ConstraintViolation:
    return ConstraintViolation(constraint_kind=kind, severity="hard", message=message)


def _longest_consecutive_run(days: set[str]) -> int:
    """ISO 日付の集合から、暦日として連続する最長の勤務日数を返す。"""
    if not days:
        return 0
    ordered = sorted(date.fromisoformat(d) for d in days)
    longest = run = 1
    for prev, cur in pairwise(ordered):
        run = run + 1 if (cur - prev).days == 1 else 1
        longest = max(longest, run)
    return longest
