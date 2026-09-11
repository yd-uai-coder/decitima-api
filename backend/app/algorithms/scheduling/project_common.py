"""Project スケジューリング strategy 共通の足回り(`travel_common.py` と同型)。

ProjectData / ProjectSolutionを受け、CPMと Difference Arrayを糊付けする

  - `parse_project_problem` … ProjectData を取り出す(型チェック)
  - `build_successors` / `build_durations` … ProjectData → CPM が食う生の dict
  - `resource_profile` … スケジュールの [start, finish) に demand を imos で区間加算 → 時刻別使用量
  - `peak_resource` … 資源使用量のピーク
  - `project_solution` … 実開始時刻 + CpmResult を ProjectSolution / CandidateSolution に詰める
  - `infeasible_project_solution` … 閉路など解なしのときの CandidateSolution

cpm strategy は「資源を無視して ES に置く」、priority_list / cp_sat は「資源を守って後ろ倒し」──
違うのは開始時刻の決め方だけなので、solution の組み立てはここに集約する(数値の drift 防止)。
"""

from __future__ import annotations

from collections.abc import Mapping

from app.algorithms.graph.topological import successors_from_edges
from app.algorithms.patterns.difference_array import range_add
from app.algorithms.scheduling.critical_path import CpmResult
from app.domain.problems.problem import OptimizationProblem
from app.domain.problems.project_manager import ProjectData
from app.domain.solutions.project_manager import ProjectSolution, ScheduledTask
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution


def parse_project_problem(problem: OptimizationProblem) -> ProjectData:
    """ProjectData を取り出す。型が違えば TypeError(select_strategy が守っている)。"""
    data = problem.data
    if not isinstance(data, ProjectData):
        raise TypeError(f"expected ProjectData, got {type(data).__name__}")
    return data


def build_successors(data: ProjectData) -> dict[str, list[str]]:
    """task -> 後続 task 群。孤立タスクも key に含む(CPM が全タスクを漏らさない)。"""
    return successors_from_edges(
        (t.id for t in data.tasks),
        ((d.predecessor, d.successor) for d in data.dependencies),
    )


def build_durations(data: ProjectData) -> dict[str, int]:
    """task -> 所要時間。"""
    return {t.id: t.duration for t in data.tasks}


def resource_profile(schedule: list[ScheduledTask], demands: Mapping[str, int]) -> list[float]:
    """時刻 t(整数)ごとの資源使用量。各タスクの [start, finish) に demand を imos で区間加算。

    Difference Array(Phase 6)の 2 人目の消費者 ── naive に毎タスク × 全時刻を舐めると
    O(タスク数 × 地平)、imos なら O(タスク数 + 地平)。
    """
    if not schedule:
        return []
    horizon = int(max(s.finish for s in schedule))
    updates = [(int(s.start), int(s.finish), float(demands.get(s.task_id, 0))) for s in schedule]

    return range_add(horizon, updates)


def peak_resource(profile: list[float]) -> float:
    """資源使用量のピーク。プロファイルが空なら 0。"""
    return max(profile, default=0.0)


def project_solution(
    data: ProjectData,
    starts: Mapping[str, int],
    cpm_result: CpmResult,
    meta: AlgorithmMeta,
    *,
    ops: int | None,
) -> CandidateSolution:
    """実開始時刻(strategy が決める)+ CpmResult(slack / critical_path / order の供給元)を詰める。

    ops=None(ライブラリトラック)なら metrics に "_ops" を入れない。資源超過の hard 判定は
    Verification(`_verify_project_resources`)── ここでは status="valid" で返す。
    """
    dur = build_durations(data)
    schedule = [
        ScheduledTask(
            task_id=t.id,
            start=float(starts[t.id]),
            finish=float(starts[t.id] + dur[t.id]),
            slack=float(cpm_result.slack.get(t.id, 0)),
        )
        for t in data.tasks
    ]
    makespan = max((s.finish for s in schedule), default=0.0)
    peak = peak_resource(resource_profile(schedule, {t.id: t.resource for t in data.tasks}))
    metrics: dict[str, float] = {"makespan": makespan, "peak_resource": peak}
    if ops is not None:
        metrics["_ops"] = float(ops)
    return CandidateSolution(
        status="valid",
        assignments=ProjectSolution(
            task_order=list(cpm_result.order),
            schedule=schedule,
            critical_path=list(cpm_result.critical_path),
            makespan=makespan,
        ),
        metrics=metrics,
        produced_by=meta,
    )


def infeasible_project_solution(meta: AlgorithmMeta) -> CandidateSolution:
    """閉路など、スケジュールが組めないときの候補解。"""
    return CandidateSolution(
        status="infeasible",
        assignments=ProjectSolution(task_order=[], schedule=[], critical_path=[], makespan=0.0),
        metrics={},
        produced_by=meta,
    )
