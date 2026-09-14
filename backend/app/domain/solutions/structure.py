"""解の「構造検証」── 制約 kind に紐づかない、解の型ごとに常に成り立つべき検査。

- verify_route_structure … 経路が連結 / 始終点 / total_weight 整合(すべて hard)
- verify_shift_structure … 割当が実在 id / 可用性 / 必要スキル / 週勤務時間 / 連続勤務日数(hard)、
  希望休(soft)。metrics(labor_cost・day_off_satisfaction・hour_variance)は `shift_metrics.py` を
  呼ぶだけ ── 探索(algorithms/scheduling)と同じコードなので数値がズレない(Phase 6-1)
- verify_network_structure … 選択リンクが実在 / 全域木の辺数 / total_weight 整合(Phase 5-3)
- verify_travel_structure … 選択 place が実在 / visit_order が選択の順列 / total_* 整合 /
  予算・時間を hard で超えない(Phase 7-3)
- verify_project_structure … task_order が全タスクの順列 / finish == start + duration /
  依存を守る(succ.start >= pred.finish)/ critical_path は slack 0 / makespan 整合(Phase 8-3)
- verify_logistics_structure … 全配送先が重複なくちょうど1台に割り当て済み / vehicle_id が
  実在・重複なし / total_distance == Σ route.distance(Phase 9-1)

"""

from __future__ import annotations

from datetime import date
from itertools import pairwise

from app.domain.problems.logistics import LogisticsData
from app.domain.problems.network_design import NetworkDesignData
from app.domain.problems.problem import OptimizationProblem
from app.domain.problems.project_manager import ProjectData
from app.domain.problems.route_planner import RouteData
from app.domain.problems.shift_scheduler import ShiftData
from app.domain.solutions.network_design import NetworkDesignSolution
from app.domain.problems.travel_planner import TravelData
from app.domain.solutions.logistics import LogisticsSolution
from app.domain.solutions.route_planner import RouteSolution
from app.domain.solutions.project_manager import ProjectSolution
from app.domain.solutions.shift_metrics import (
    assignment_metrics,
    distinct,
    hours_by_staff,
    working_days_by_staff,
)
from app.domain.solutions.shift_scheduler import ShiftSolution
from app.domain.solutions.solution import CandidateSolution, ConstraintViolation
from app.domain.solutions.travel_planner import TravelSolution


def structural_verify(
    problem: OptimizationProblem, solution: CandidateSolution
) -> tuple[list[ConstraintViolation], dict[str, float]]:
    """解の型を見て対応する構造検証にディスパッチ。(違反リスト, 追加メトリクス) を返す。"""
    assignments = solution.assignments
    if isinstance(assignments, RouteSolution) and isinstance(problem.data, RouteData):
        return verify_route_structure(problem.data, assignments), {}
    if isinstance(assignments, ShiftSolution) and isinstance(problem.data, ShiftData):
        return verify_shift_structure(problem.data, assignments)
    if isinstance(assignments, NetworkDesignSolution) and isinstance(
        problem.data, NetworkDesignData
    ):
        return verify_network_structure(problem.data, assignments), {}
    if isinstance(assignments, TravelSolution) and isinstance(
        problem.data, TravelData
    ):
        return verify_travel_structure(problem.data, assignments), {}
    if isinstance(assignments, ProjectSolution) and isinstance(
        problem.data, ProjectData
    ):
        return verify_project_structure(problem.data, assignments), {}
    if isinstance(assignments, LogisticsSolution) and isinstance(
        problem.data, LogisticsData
    ):
        return verify_logistics_structure(problem.data, assignments), {}
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
# travel
# ---------------------------------------------------------------------------


def verify_travel_structure(data: TravelData, sol: TravelSolution) -> list[ConstraintViolation]:
    """旅行プランの「形」を検証(純粋述語のみ)。

    移動費用の再計算(Floyd-Warshall)は「計算」なので SolutionVerificationService が
    `travel_common.tour_cost` で行う(network の全域木判定と同じ切り分け。`Phase-2-2.md` §3)。
    ここは「選択が実在 / 順序が集合と一致 / 効用の和 / 予算・時間の宣言値が上限内」だけ。
    """
    out: list[ConstraintViolation] = []
    place_by_id = {p.id: p for p in data.places}

    unknown = [pid for pid in sol.selected_place_ids if pid not in place_by_id]
    for pid in unknown:
        out.append(_hard("travel_structure", f"unknown place {pid!r} in solution"))

    if set(sol.visit_order) != set(sol.selected_place_ids):
        out.append(
            _hard("travel_structure", "visit_order is not a permutation of selected_place_ids")
        )
    if len(sol.visit_order) != len(set(sol.visit_order)):
        out.append(_hard("travel_structure", "visit_order has duplicates"))

    known_visit = [pid for pid in sol.visit_order if pid in place_by_id]
    value = sum(place_by_id[pid].value * data.preferences.get(pid, 1.0) for pid in known_visit)
    if abs(value - sol.total_value) > 1e-9:
        out.append(
            _hard("travel_structure", f"total_value {sol.total_value} != utility sum {value}")
        )

    if sol.total_cost > data.budget + 1e-9:
        out.append(
            _hard("travel_structure", f"total_cost {sol.total_cost} exceeds budget {data.budget}")
        )
    if sol.total_time > data.time_budget + 1e-9:
        out.append(
            _hard(
                "travel_structure",
                f"total_time {sol.total_time} exceeds time_budget {data.time_budget}",
            )
        )
    return out


# ---------------------------------------------------------------------------
# project
# ---------------------------------------------------------------------------


def verify_project_structure(data: ProjectData, sol: ProjectSolution) -> list[ConstraintViolation]:
    """スケジュールの「形」を検証(純粋述語のみ)。すべて hard。

    資源プロファイルの再計算(imos)は「計算」なので SolutionVerificationService が
    `project_common.resource_profile` で行う(travel の tour_cost 検算と同じ切り分け)。
    ここは「順列 / 所要時間 / 依存 / クリティカルパス / makespan」の整合だけ。
    """
    out: list[ConstraintViolation] = []
    task_ids = {t.id for t in data.tasks}
    dur = {t.id: t.duration for t in data.tasks}
    sched = {s.task_id: s for s in sol.schedule}

    if set(sol.task_order) != task_ids or len(sol.task_order) != len(task_ids):
        out.append(_hard("project_structure", "task_order is not a permutation of all tasks"))
    if set(sched) != task_ids or len(sol.schedule) != len(task_ids):
        out.append(_hard("project_structure", "schedule does not cover every task exactly once"))

    for s in sol.schedule:
        d = dur.get(s.task_id)
        if d is not None and abs(s.finish - (s.start + d)) > 1e-9:
            out.append(
                _hard(
                    "project_structure",
                    f"task {s.task_id!r}: finish {s.finish} != start {s.start} + duration {d}",
                )
            )

    # 依存: successor は predecessor が終わってから始まる(finish-to-start)
    for dep in data.dependencies:
        p, q = sched.get(dep.predecessor), sched.get(dep.successor)
        if p is not None and q is not None and q.start < p.finish - 1e-9:
            out.append(
                _hard(
                    "project_structure",
                    f"dependency {dep.id!r}: {dep.successor!r} starts at {q.start} "
                    f"before {dep.predecessor!r} finishes at {p.finish}",
                )
            )

    # クリティカルパスのタスクは余裕ゼロ
    for tid in sol.critical_path:
        s = sched.get(tid)
        if s is not None and abs(s.slack) > 1e-9:
            out.append(
                _hard(
                    "project_structure",
                    f"critical_path task {tid!r} has non-zero slack {s.slack}",
                )
            )

    if sol.schedule:
        real_makespan = max(s.finish for s in sol.schedule)
        if abs(real_makespan - sol.makespan) > 1e-9:
            out.append(
                _hard(
                    "project_structure",
                    f"makespan {sol.makespan} != max finish {real_makespan}",
                )
            )
    return out


# ---------------------------------------------------------------------------
# logistics
# ---------------------------------------------------------------------------


def verify_logistics_structure(
    data: LogisticsData, sol: LogisticsSolution
) -> list[ConstraintViolation]:
    """配送計画の「形」を検証(純粋述語のみ)。すべて hard。

    容量の再チェックと距離の再計算(Floyd-Warshall)は「計算」なので
    SolutionVerificationService が `logistics_common` で行う。ここは「全配送先が
    重複なく割り当て済み / vehicle_id が実在・重複なし / total_distance の整合」だけ。
    """
    out: list[ConstraintViolation] = []
    delivery_ids = {d.id for d in data.deliveries}
    vehicle_ids = {v.id for v in data.vehicles}

    used_vehicle_ids = [r.vehicle_id for r in sol.routes]
    if len(used_vehicle_ids) != len(set(used_vehicle_ids)):
        out.append(_hard("logistics_structure", "the same vehicle appears in multiple routes"))
    unknown_vehicles = [vid for vid in used_vehicle_ids if vid not in vehicle_ids]
    for vid in unknown_vehicles:
        out.append(_hard("logistics_structure", f"unknown vehicle {vid!r} in solution"))

    all_stop_ids = [sid for r in sol.routes for sid in r.stop_ids]
    if len(all_stop_ids) != len(set(all_stop_ids)):
        out.append(_hard("logistics_structure", "a delivery appears in more than one route"))
    if set(all_stop_ids) != delivery_ids:
        missing = delivery_ids - set(all_stop_ids)
        extra = set(all_stop_ids) - delivery_ids
        out.append(
            _hard(
                "logistics_structure",
                f"routes do not cover every delivery exactly once "
                f"(missing={sorted(missing)}, unknown={sorted(extra)})",
            )
        )

    total = sum(r.distance for r in sol.routes)
    if abs(total - sol.total_distance) > 1e-9:
        out.append(
            _hard(
                "logistics_structure",
                f"total_distance {sol.total_distance} != route sum {total}",
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
