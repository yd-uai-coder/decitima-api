"""problem_type ごとの「ベース問題」── LLM が自然言語から埋めてよいのは objectives /
constraints / data のトップレベル・スカラーまでで、ノード/エッジ/タスクのようなカタログ
(list)フィールドはここに定義した既存の問題から常に引き継ぐ。

"""

from __future__ import annotations

from app.domain.problems.logistics import (
    DeliveryStop,
    LogisticsData,
    LogisticsNode,
    RoadSegment,
    Vehicle,
)
from app.domain.problems.network_design import NetworkDesignData, NetworkLink, NetworkNode
from app.domain.problems.problem import Objective, OptimizationProblem, StaffingConstraint
from app.domain.problems.project_manager import ProjectData, ProjectTask, TaskDependency
from app.domain.problems.route_planner import RouteData, RouteEdge, RouteNode
from app.domain.problems.shift_scheduler import ShiftData, ShiftSlot, Staff
from app.domain.problems.travel_planner import Place, TravelData, TravelLeg

_ROUTE_BASE = OptimizationProblem(
    problem_type="route_planning",
    objectives=[Objective(sense="minimize", target="total_weight")],
    data=RouteData(
        nodes=[
            RouteNode(id="A", label="駅"),
            RouteNode(id="B", label="公園"),
            RouteNode(id="C", label="美術館"),
            RouteNode(id="D", label="病院"),
            RouteNode(id="E", label="ホテル"),
        ],
        edges=[
            RouteEdge(id="e_ab", source="A", target="B", weight=2),
            RouteEdge(id="e_bc", source="B", target="C", weight=3),
            RouteEdge(id="e_bd", source="B", target="D", weight=1),
            RouteEdge(id="e_ce", source="C", target="E", weight=4),
            RouteEdge(id="e_de", source="D", target="E", weight=2),
        ],
        start="A",
        goal="E",
    ),
)

_NETWORK_DESIGN_BASE = OptimizationProblem(
    problem_type="network_design",
    objectives=[Objective(sense="minimize", target="total_weight")],
    data=NetworkDesignData(
        nodes=[
            NetworkNode(id="A", label="本社"),
            NetworkNode(id="B", label="支社A"),
            NetworkNode(id="C", label="支社B"),
            NetworkNode(id="D", label="支社C"),
            NetworkNode(id="E", label="支社D"),
        ],
        links=[
            NetworkLink(id="L_ab", endpoints=("A", "B"), weight=1),
            NetworkLink(id="L_bc", endpoints=("B", "C"), weight=2),
            NetworkLink(id="L_cd", endpoints=("C", "D"), weight=3),
            NetworkLink(id="L_be", endpoints=("B", "E"), weight=4),
            NetworkLink(id="L_ac", endpoints=("A", "C"), weight=5),
            NetworkLink(id="L_de", endpoints=("D", "E"), weight=6),
            NetworkLink(id="L_ae", endpoints=("A", "E"), weight=7),
        ],
    ),
)

_SHIFT_BASE = OptimizationProblem(
    problem_type="shift_scheduling",
    objectives=[
        Objective(sense="minimize", target="labor_cost", weight=0.7),
        Objective(sense="maximize", target="day_off_satisfaction", weight=0.3),
    ],
    constraints=[StaffingConstraint(severity="hard")],
    data=ShiftData(
        staff=[
            Staff(
                id="tanaka",
                name="田中",
                hourly_wage=1200,
                available_slot_ids=["s1", "s2", "s3", "s4"],
            ),
            Staff(
                id="sato",
                name="佐藤",
                hourly_wage=1000,
                available_slot_ids=["s1", "s2", "s3", "s4"],
            ),
            Staff(id="ito", name="伊藤", hourly_wage=1100, available_slot_ids=["s1", "s3"]),
        ],
        slots=[
            ShiftSlot(id="s1", day="2026-09-01", start_hour=9, end_hour=14, required_headcount=1),
            ShiftSlot(id="s2", day="2026-09-01", start_hour=14, end_hour=19, required_headcount=1),
            ShiftSlot(id="s3", day="2026-09-02", start_hour=9, end_hour=14, required_headcount=1),
            ShiftSlot(id="s4", day="2026-09-02", start_hour=14, end_hour=19, required_headcount=1),
        ],
        max_weekly_hours=40,
        max_consecutive_days=5,
    ),
)

# 予算・期間・好みは README §3.1 の例(「5万円以内で東京を2日間旅行したい。食事を重視して、
# 移動時間はできるだけ短くしたい。浅草には必ず行きたい。」)に沿って LLM が上書きする前提の
# 初期値。P1 の id/name が「浅草」の grounding 対象になる。
_TRAVEL_BASE = OptimizationProblem(
    problem_type="travel_planning",
    objectives=[Objective(sense="maximize", target="total_value")],
    data=TravelData(
        places=[
            Place(id="P0", name="宿", value=0, cost=0, duration=0),
            Place(id="P1", name="浅草", value=10, cost=0, duration=2),
            Place(id="P2", name="美術館", value=8, cost=1500, duration=2),
            Place(id="P3", name="公園", value=6, cost=0, duration=1),
            Place(id="P4", name="展望台", value=12, cost=3000, duration=1.5),
        ],
        legs=[
            TravelLeg(id=f"L{a}{b}", endpoints=(f"P{a}", f"P{b}"), travel_cost=500, travel_time=0.5)
            for a in range(5)
            for b in range(a + 1, 5)
        ],
        budget=15000,
        time_budget=16,
        start="P0",
        preferences={},
    ),
)

_PROJECT_BASE = OptimizationProblem(
    problem_type="project_scheduling",
    objectives=[
        Objective(sense="minimize", target="makespan"),
        Objective(sense="minimize", target="peak_resource", weight=0.1),
    ],
    data=ProjectData(
        tasks=[
            ProjectTask(id="A", name="設計", duration=3, resource=2),
            ProjectTask(id="B", name="調達", duration=2, resource=1),
            ProjectTask(id="C", name="実装", duration=4, resource=3),
            ProjectTask(id="D", name="検証", duration=2, resource=1),
            ProjectTask(id="E", name="リリース", duration=1, resource=2),
        ],
        dependencies=[
            TaskDependency(id="dep_ac", predecessor="A", successor="C"),
            TaskDependency(id="dep_bd", predecessor="B", successor="D"),
            TaskDependency(id="dep_ce", predecessor="C", successor="E"),
            TaskDependency(id="dep_de", predecessor="D", successor="E"),
        ],
        resource_capacity=3,
    ),
)

_LOGISTICS_BASE = OptimizationProblem(
    problem_type="logistics_planning",
    objectives=[Objective(sense="minimize", target="total_distance")],
    data=LogisticsData(
        depot_id="D",
        nodes=[
            LogisticsNode(id="D", label="倉庫"),
            LogisticsNode(id="N1", label="A地区"),
            LogisticsNode(id="N2", label="B地区"),
            LogisticsNode(id="N3", label="C地区"),
        ],
        segments=[
            RoadSegment(id="S_D1", source="D", target="N1", distance=4),
            RoadSegment(id="S_D2", source="D", target="N2", distance=3),
            RoadSegment(id="S_D3", source="D", target="N3", distance=6),
            RoadSegment(id="S_12", source="N1", target="N2", distance=2),
            RoadSegment(id="S_23", source="N2", target="N3", distance=3),
        ],
        vehicles=[
            Vehicle(id="V1", capacity_weight=10, capacity_volume=10),
            Vehicle(id="V2", capacity_weight=10, capacity_volume=10),
        ],
        deliveries=[
            DeliveryStop(id="P1", node_id="N1", demand_weight=4, demand_volume=4),
            DeliveryStop(id="P2", node_id="N2", demand_weight=5, demand_volume=5),
            DeliveryStop(id="P3", node_id="N3", demand_weight=7, demand_volume=7),
        ],
    ),
)

BASE_PROBLEMS: dict[str, OptimizationProblem] = {
    "route_planning": _ROUTE_BASE,
    "network_design": _NETWORK_DESIGN_BASE,
    "shift_scheduling": _SHIFT_BASE,
    "travel_planning": _TRAVEL_BASE,
    "project_scheduling": _PROJECT_BASE,
    "logistics_planning": _LOGISTICS_BASE,
}


def get_base_problem(problem_type: str) -> OptimizationProblem:
    """problem_type に対応するベース問題を、呼び出しごとに独立した deep copy で返す。"""
    return BASE_PROBLEMS[problem_type].model_copy(deep=True)
