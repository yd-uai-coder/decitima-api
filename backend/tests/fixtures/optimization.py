"""テスト用の問題・解ビルダー。

decitima-api の pyproject は pythonpath=["."] なので `from tests.fixtures.optimization import ...`
で import できる。Phase 2 で shift の解ビルダーと infeasible な shift 問題を追加。

(route):
  - build_scaled_route_problem に `density`(横エッジの本数を振れる。既定は Phase 3 と同じ挙動)
  - build_negative_route_problem … 有向 + 負辺(Bellman-Ford 用。無向だと負辺は即・負閉路)
  - build_negative_cycle_route_problem … 有向の負閉路
  - build_coord_route_problem … 座標つき(A* のヒューリスティック用)
(network):
  - build_network_problem / build_network_solution … network_design(MST)
  - build_disconnected_network_problem … 孤立ノードあり(infeasible 用)
(travel):
  - build_travel_problem / build_travel_solution … travel_planning(Knapsack DP)
  - build_scaled_travel_problem … place 数を振れる(規模別の analysis 用)
(project):
  - build_project_problem / build_project_solution … project_scheduling(CPM / RCPSP)
  - build_scaled_project_problem … タスク数を振れる(ランダム DAG)
  - build_cyclic_project_problem … 依存が閉路(validation の infeasible 用)
(logistics):
  - build_logistics_problem / build_logistics_solution … logistics_planning(CVRP)
  - build_scaled_logistics_problem … 配送先数を振れる(規模別の比較・プロパティテスト用)
  - build_disconnected_logistics_problem … 配送先がデポと非連結(validation の infeasible 用)
"""


from __future__ import annotations

import random

from app.domain.problems.network_design import (
    NetworkDesignData,
    NetworkLink,
    NetworkNode,
)

from app.domain.problems.problem import (
    ForbiddenConstraint,
    GenericConstraint,
    NumericBoundConstraint,
    Objective,
    OptimizationProblem,
    RequiredInclusionConstraint,
    StaffingConstraint,
)
from app.domain.problems.logistics import (
    DeliveryStop,
    LogisticsData,
    LogisticsNode,
    RoadSegment,
    Vehicle,
)
from app.domain.problems.route_planner import RouteData, RouteEdge, RouteNode
from app.domain.problems.shift_scheduler import ShiftData, ShiftSlot, Staff
from app.domain.solutions.shift_scheduler import ShiftSolution
from app.domain.solutions.solution import (
    AlgorithmMeta,
    CandidateSolution,
    SolutionStatus,
)

from app.domain.solutions.network_design import NetworkDesignSolution
from app.domain.solutions.travel_planner import TravelSolution
from app.domain.problems.travel_planner import Place, TravelData, TravelLeg
from app.domain.problems.project_manager import ProjectData, ProjectTask, TaskDependency
from app.domain.solutions.project_manager import ProjectSolution, ScheduledTask
from app.domain.solutions.logistics import LogisticsSolution, VehicleRoute


# Phase 0-2 §7.1 の例題:
#   「A から E まで最短で行きたい。ただし橋(edge e_bd)は工事中で通れない。C は必ず経由する。」
#   期待解: A -> B -> C -> E, total_weight = 9


# 無向グラフ
_UNDIRECTED_ROUTE_EDGES = [
    RouteEdge(id="e_ab", source="A", target="B", weight=2),
    RouteEdge(id="e_bc", source="B", target="C", weight=3),
    RouteEdge(id="e_bd", source="B", target="D", weight=1),
    RouteEdge(id="e_ce", source="C", target="E", weight=4),
    RouteEdge(id="e_de", source="D", target="E", weight=2),
]

def build_route_problem(
    *,
    forbidden: list[str] | None = None,
    required: list[str] | None = None,
    max_total_weight: float | None = None,
    start: str = "A",
    goal: str = "E",
) -> OptimizationProblem:
    """例題の Route Planner。制約を差し替えて色々なケースを作れる。"""
    constraints: list = []
    if forbidden:
        constraints.append(ForbiddenConstraint(severity="hard", items=forbidden))
    if required:
        constraints.append(RequiredInclusionConstraint(severity="hard", items=required))
    if max_total_weight is not None:
        # Dijkstra はこの上限を無視して最短路を出す → Verification が invalid にする(Phase-2-6)
        constraints.append(
            NumericBoundConstraint(
                severity="hard", field="total_weight", operator="<=", value=max_total_weight
            )
        )
    return OptimizationProblem(
        problem_type="route_planning",
        objectives=[Objective(sense="minimize", target="total_weight")],
        constraints=constraints,
        data=RouteData(
            nodes=[RouteNode(id=n) for n in ["A", "B", "C", "D", "E"]],
            edges=list(_UNDIRECTED_ROUTE_EDGES),
            start=start,
            goal=goal,
        ),
    )


def build_negative_route_problem() -> OptimizationProblem:
    """有向グラフ + 負辺(負閉路は無し)。S->A->B->T の負辺経路が S->T 直行より短い。

    直行 S->T = 5、S->A(2) + A->B(-4) + B->T(3) = 1。Dijkstra は S->T を settle して
    誤答するので、Bellman-Ford の出番。allow_negative=True。
    """
    return OptimizationProblem(
        problem_type="route_planning",
        objectives=[Objective(sense="minimize", target="total_weight")],
        data=RouteData(
            nodes=[RouteNode(id=n) for n in ["S", "A", "B", "T"]],
            edges=[
                RouteEdge(id="s_t", source="S", target="T", weight=5, directed=True),
                RouteEdge(id="s_a", source="S", target="A", weight=2, directed=True),
                RouteEdge(id="a_b", source="A", target="B", weight=-4, directed=True),
                RouteEdge(id="b_t", source="B", target="T", weight=3, directed=True),
            ],
            start="S",
            goal="T",
            allow_negative=True,
        ),
    )


def build_negative_cycle_route_problem() -> OptimizationProblem:
    """有向の負閉路(A->B->C->A の和が負)。start から到達でき、最短経路は定義できない。"""
    return OptimizationProblem(
        problem_type="route_planning",
        objectives=[Objective(sense="minimize", target="total_weight")],
        data=RouteData(
            nodes=[RouteNode(id=n) for n in ["S", "A", "B", "C", "T"]],
            edges=[
                RouteEdge(id="s_a", source="S", target="A", weight=1, directed=True),
                RouteEdge(id="a_b", source="A", target="B", weight=1, directed=True),
                RouteEdge(id="b_c", source="B", target="C", weight=-1, directed=True),
                RouteEdge(id="c_a", source="C", target="A", weight=-2, directed=True),
                RouteEdge(id="b_t", source="B", target="T", weight=1, directed=True),
            ],
            start="S",
            goal="T",
            allow_negative=True,
        ),
    )


def build_coord_route_problem(*, required: list[str] | None = None) -> OptimizationProblem:
    """座標つきグラフ。weight は両端の直線距離なので euclidean ヒューリスティックは可容。

    直線ハイウェイ P0(x=0)..P6(x=6) に、goal と逆方向(x<0)へ伸びる寄り道クラスタ D0..D3 を
    P1 からぶら下げる。Dijkstra は g が小さい D ノードも settle するが、A* は h(Dk, goal) が
    大きいので P チェーンを先に伸ばして goal に着き、D を pop しない ── `_ops` が下がる。
    """
    nodes = [RouteNode(id=f"P{i}", x=float(i), y=0.0) for i in range(7)]
    edges = [
        RouteEdge(id=f"p{i}", source=f"P{i}", target=f"P{i + 1}", weight=1.0) for i in range(6)
    ]
    for k in range(4):
        nodes.append(RouteNode(id=f"D{k}", x=-1.0 - k, y=0.0))
        src = "P1" if k == 0 else f"D{k - 1}"
        edges.append(RouteEdge(id=f"d{k}", source=src, target=f"D{k}", weight=1.0))

    constraints: list = []
    if required:
        constraints.append(RequiredInclusionConstraint(severity="hard", items=required))
    return OptimizationProblem(
        problem_type="route_planning",
        objectives=[Objective(sense="minimize", target="total_weight")],
        constraints=constraints,
        data=RouteData(nodes=nodes, edges=edges, start="P0", goal="P6"),
    )


def build_scaled_route_problem(
    n: int, *, seed: int = 0, density: float = 0.5
) -> OptimizationProblem:
    """seed 固定のランダムな連結グラフ。start = 先頭ノード, goal = 末尾ノード。

    連鎖 n0-n1-...-n(n-1) を必ず張って連結性を保証し、ランダムな横エッジを int(n*density) 本足す。
    density=0.5(既定)なら Phase 3 と同じ本数(n//2)。密度を上げると経路の選択肢が増える。
    """
    if n < 2:
        raise ValueError(f"n must be >= 2, got {n}")
    rng = random.Random(seed)
    ids = [f"n{i}" for i in range(n)]
    edges: list[RouteEdge] = []
    for i in range(n - 1):
        w = float(rng.randint(1, 9))
        edges.append(RouteEdge(id=f"e{i}_{i + 1}", source=ids[i], target=ids[i + 1], weight=w))
    for k in range(int(n * density)):
        a, b = rng.sample(range(n), 2)
        w = float(rng.randint(1, 9))
        edges.append(RouteEdge(id=f"x{k}_{a}_{b}", source=ids[a], target=ids[b], weight=w))
    return OptimizationProblem(
        problem_type="route_planning",
        objectives=[Objective(sense="minimize", target="total_weight")],
        data=RouteData(
            nodes=[RouteNode(id=i) for i in ids],
            edges=edges,
            start=ids[0],
            goal=ids[-1],
        ),
    )


# -----------------------------------------
# Benchmark
# -----------------------------------------

def build_scaled_route_problem(n: int, *, seed: int = 0) -> OptimizationProblem:
    """seed 固定のランダムな連結グラフ。start = 先頭ノード, goal = 末尾ノード。

    連鎖 n0-n1-...-n(n-1) を必ず張って連結性を保証し、ランダムな横エッジを n//2 本足す。
    n を振れば入力サイズ別カーブ、seed を振ればオラクルのプロパティテストに使える。
    """
    if n < 2:
        raise ValueError(f"n must be >= 2, got {n}") # ノードが2つ以上なければエラー
    rng = random.Random(seed) # seedは乱数生成器のスタート地点：seed値が同じならrandom.Randomの結果が同じになる
    ids = [f"n{i}" for i in range(n)]
    edges: list[RouteEdge] = []
    # 連鎖(連結性の保証)
    for i in range(n - 1):
        w = float(rng.randint(1, 9))
        # 重み付のエッジを生成していく
        edges.append(RouteEdge(id=f"e{i}_{i + 1}", source=ids[i], target=ids[i + 1], weight=w))

    # 追加の横エッジ
    for k in range(n // 2):
        # 0からn-1でランダムの組み合わせを決める -> 後にエッジになる
        a, b = rng.sample(range(n), 2)
        w = float(rng.randint(1, 9))
        # 重み付のエッジを生成していく
        edges.append(RouteEdge(id=f"x{k}_{a}_{b}", source=ids[a], target=ids[b], weight=w))

    return OptimizationProblem(
        problem_type="route_planning",
        objectives=[Objective(sense="minimize", target="total_weight")],
        data=RouteData(
            nodes=[RouteNode(id=i) for i in ids], edges=edges, start=ids[0], goal=ids[-1]
        ),
    )

# ---------------------------------------------------------------------------
# network_design(MST)
# ---------------------------------------------------------------------------

# 5 拠点。既知の MST: L_ab(1) + L_bc(2) + L_cd(3) + L_be(4) = 10
_NETWORK_LINKS = [
    NetworkLink(id="L_ab", endpoints=("A", "B"), weight=1),
    NetworkLink(id="L_bc", endpoints=("B", "C"), weight=2),
    NetworkLink(id="L_cd", endpoints=("C", "D"), weight=3),
    NetworkLink(id="L_be", endpoints=("B", "E"), weight=4),
    NetworkLink(id="L_ac", endpoints=("A", "C"), weight=5),
    NetworkLink(id="L_de", endpoints=("D", "E"), weight=6),
    NetworkLink(id="L_ae", endpoints=("A", "E"), weight=7),
]

def build_network_problem(
    *,
    forbidden: list[str] | None = None,
    required: list[str] | None = None,
    max_total_weight: float | None = None,
) -> OptimizationProblem:
    """例題の Network Designer。MST の総コストは 10。"""
    constraints: list = []
    if forbidden:
        constraints.append(ForbiddenConstraint(severity="hard", items=forbidden))
    if required:
        constraints.append(RequiredInclusionConstraint(severity="hard", items=required))
    if max_total_weight is not None:
        constraints.append(
            NumericBoundConstraint(
                severity="hard",
                field="total_weight",
                operator="<=",
                value=max_total_weight,
            )
        )
    return OptimizationProblem(
        problem_type="network_design",
        objectives=[Objective(sense="minimize", target="total_weight")],
        constraints=constraints,
        data=NetworkDesignData(
            nodes=[NetworkNode(id=n) for n in ["A", "B", "C", "D", "E"]],
            links=list(_NETWORK_LINKS),
        ),
    )


def build_disconnected_network_problem() -> OptimizationProblem:
    """拠点 C が孤立 ── どのリンクも C に繋がらないので全域木は作れない(infeasible)。"""
    return OptimizationProblem(
        problem_type="network_design",
        objectives=[Objective(sense="minimize", target="total_weight")],
        data=NetworkDesignData(
            nodes=[NetworkNode(id=n) for n in ["A", "B", "C"]],
            links=[NetworkLink(id="L_ab", endpoints=("A", "B"), weight=1)],
        ),
    )


def build_network_solution(
    selected_link_ids: list[str],
    total_weight: float,
    *,
    status: SolutionStatus = "valid",
) -> CandidateSolution:
    """手組みの NetworkDesignSolution を CandidateSolution に包む。"""
    return CandidateSolution(
        status=status,
        assignments=NetworkDesignSolution(
            selected_link_ids=selected_link_ids, total_weight=total_weight
        ),
        produced_by=AlgorithmMeta(name="manual", family="graph", implementation="fixture"),
    )

# ---------------------------------------------------------------------------
# shift
# ---------------------------------------------------------------------------


def _slot(slot_id: str, day: str, start: int, end: int, headcount: int = 1) -> ShiftSlot:
    return ShiftSlot(
        id=slot_id, day=day, start_hour=start, end_hour=end, required_headcount=headcount
    )


def build_shift_problem(
    *, with_days_off_penalty: bool = False, with_hour_variance: bool = False
        ) -> OptimizationProblem:
    """Phase 0-2 §7.2 の例題。4 スロット × 各 required_headcount=1。

    有効解の一例: {s1:[tanaka], s2:[sato], s3:[ito], s4:[tanaka]}
      - tanaka は s4(2026-09-02)を希望休にしている → soft 違反
    """
    constraints: list = [StaffingConstraint(severity="hard")]
    if with_days_off_penalty:
        constraints.append(GenericConstraint(kind="respect_days_off", severity="soft", penalty=5.0))
    objectives = [
        Objective(sense="minimize", target="labor_cost", weight=0.7),
        Objective(sense="maximize", target="day_off_satisfaction", weight=0.3),
    ]
    if with_hour_variance:
        objectives.append(Objective(sense="minimize", target="hour_variance", weight=100.0))
    return OptimizationProblem(
        problem_type="shift_scheduling",
        objectives=[
            Objective(sense="minimize", target="labor_cost", weight=0.7),
            Objective(sense="maximize", target="day_off_satisfaction", weight=0.3),
        ],
        constraints=constraints,
        data=ShiftData(
            staff=[
                Staff(
                    id="tanaka",
                    hourly_wage=1200,
                    available_slot_ids=["s1", "s2", "s3", "s4"],
                    requested_days_off=["2026-09-02"],
                ),
                Staff(id="sato", hourly_wage=1000, available_slot_ids=["s1", "s2", "s3", "s4"]),
                Staff(id="ito", hourly_wage=1100, available_slot_ids=["s1", "s3"]),
            ],
            slots=[
                _slot("s1", "2026-09-01", 9, 14),
                _slot("s2", "2026-09-01", 14, 19),
                _slot("s3", "2026-09-02", 9, 14),
                _slot("s4", "2026-09-02", 14, 19),
            ],
            max_weekly_hours=20,
            max_consecutive_days=5,
        ),
    )


def build_infeasible_shift_problem() -> OptimizationProblem:
    """s1 が 2 人必要なのに s1 に入れるスタッフが 1 人だけ ── Semantic Validation で弾かれる。"""
    return OptimizationProblem(
        problem_type="shift_scheduling",
        objectives=[Objective(sense="minimize", target="labor_cost")],
        constraints=[StaffingConstraint(severity="hard")],
        data=ShiftData(
            staff=[Staff(id="only", hourly_wage=1000, available_slot_ids=["s1"])],
            slots=[_slot("s1", "2026-09-01", 9, 14, headcount=2)],
        ),
    )


def build_scaled_shift_problem(
    n_staff: int, n_days: int, *, slots_per_day: int = 2, seed: int = 0
) -> OptimizationProblem:
    """規模を振れるシフト問題(手実装の破綻を実測する Phase 6-6 用)。

    `build_scaled_route_problem` と同型 ── seed 固定で RNG 呼び出し順を固定し決定論に。
    スタッフは全スロット可用・スキルなし。スロットは 1 日 `slots_per_day` 本、各 headcount=1。
    """
    rng = random.Random(seed)
    slot_ids = [f"d{d}_s{k}" for d in range(n_days) for k in range(slots_per_day)]
    staff = [
        Staff(
            id=f"st{i}",
            hourly_wage=float(rng.randrange(900, 1400, 50)),
            available_slot_ids=list(slot_ids),
            requested_days_off=(
                [f"2026-09-{1 + rng.randrange(n_days):02d}"] if rng.random() < 0.3 else []
            ),
        )
        for i in range(n_staff)
    ]
    slots = [
        _slot(
            f"d{d}_s{k}",
            f"2026-09-{1 + d:02d}",
            9 + 5 * k,
            14 + 5 * k,
        )
        for d in range(n_days)
        for k in range(slots_per_day)
    ]
    return OptimizationProblem(
        problem_type="shift_scheduling",
        objectives=[
            Objective(sense="minimize", target="labor_cost", weight=0.7),
            Objective(sense="maximize", target="day_off_satisfaction", weight=0.3),
        ],
        constraints=[StaffingConstraint(severity="hard")],
        data=ShiftData(staff=staff, slots=slots, max_weekly_hours=40, max_consecutive_days=n_days),
    )


def build_shift_solution(
    assignments: dict[str, list[str]], *, status: SolutionStatus = "valid"
) -> CandidateSolution:
    
    """手組みの ShiftSolution を CandidateSolution に包む(shift を解く strategy は Phase 5)。"""
    return CandidateSolution(
        status=status,
        assignments=ShiftSolution(assignments=assignments),
        produced_by=AlgorithmMeta(name="manual", family="scheduling", implementation="fixture"),
    )


# ---------------------------------------------------------------------------
# travel_planning(Knapsack DP)── Phase 7  # (Phase 7-3) ここから下は 7-3 の成果物
# ---------------------------------------------------------------------------

# 5 拠点。P0 を起点(home)にして予算・時間内で好み加重の効用を最大化する。
# legs は 5 拠点の(ほぼ)完全グラフ、移動は一律 cost 1 / time 1。
#   place cost 合計(P1..P4)= 18、time 合計 = 9。閉路(P0 に戻る)の移動は 訪問数+1 本。
_TRAVEL_PLACES = [
    Place(id="P0", name="home", value=0, cost=0, duration=0),
    Place(id="P1", name="museum", value=10, cost=4, duration=2),
    Place(id="P2", name="park", value=8, cost=3, duration=3),
    Place(id="P3", name="market", value=6, cost=5, duration=1),
    Place(id="P4", name="tower", value=12, cost=6, duration=3),
]
_TRAVEL_LEGS = [
    TravelLeg(id=f"L{a}{b}", endpoints=(f"P{a}", f"P{b}"), travel_cost=1, travel_time=1)
    for a in range(5)
    for b in range(a + 1, 5)
]


def build_travel_problem(
    *,
    budget: float = 25,
    time_budget: float = 20,
    start: str | None = "P0",
    forbidden: list[str] | None = None,
    required: list[str] | None = None,
    preferences: dict[str, float] | None = None,
) -> OptimizationProblem:
    """例題の Travel Planner。DP / Greedy / BruteForce をかける。"""
    constraints: list = []
    if forbidden:
        constraints.append(ForbiddenConstraint(severity="hard", items=forbidden))
    if required:
        constraints.append(RequiredInclusionConstraint(severity="hard", items=required))
    return OptimizationProblem(
        problem_type="travel_planning",
        objectives=[Objective(sense="maximize", target="total_value")],
        constraints=constraints,
        data=TravelData(
            places=list(_TRAVEL_PLACES),
            legs=list(_TRAVEL_LEGS),
            budget=budget,
            time_budget=time_budget,
            start=start,
            preferences=preferences or {},
        ),
    )


def build_scaled_travel_problem(
    n_places: int, seed: int = 0, *, budget: float = 20, time_budget: float = 20
) -> OptimizationProblem:
    """place を n_places 個ランダム生成した Travel 問題(規模別の analysis / プロパティテスト用)。

    legs は「一直線に繋ぐ + seed で数本の近道」。RNG の呼び出し順を固定して決定論を保つ。
    `budget`/`time_budget` は既定 20(Phase 3〜9 時点の挙動)── Phase 15-2 で knapsack_dp の
    DP グリッド肥大化を実測するために引数化した。
    """
    rng = random.Random(seed)
    places = [Place(id="P0", name="home", value=0, cost=0, duration=0)]
    for i in range(1, n_places):
        places.append(
            Place(
                id=f"P{i}",
                value=rng.randint(1, 15),
                cost=rng.randint(1, 6),
                duration=rng.randint(1, 5),
            )
        )
    legs = [
        TravelLeg(
            id=f"L{i}",
            endpoints=(f"P{i}", f"P{i + 1}"),
            travel_cost=rng.randint(1, 3),
            travel_time=rng.randint(1, 3),
        )
        for i in range(n_places - 1)
    ]
    for k in range(max(n_places // 4, 1)):
        a, b = sorted(rng.sample(range(n_places), 2))
        legs.append(
            TravelLeg(
                id=f"S{k}",
                endpoints=(f"P{a}", f"P{b}"),
                travel_cost=rng.randint(2, 5),
                travel_time=rng.randint(2, 5),
            )
        )
    return OptimizationProblem(
        problem_type="travel_planning",
        objectives=[Objective(sense="maximize", target="total_value")],
        constraints=[],
        data=TravelData(
            places=places,
            legs=legs,
            budget=budget,
            time_budget=time_budget,
            start="P0",
            preferences={},
        ),
    )


def build_travel_solution(
    selected_place_ids: list[str],
    visit_order: list[str],
    *,
    total_value: float = 0.0,
    total_cost: float = 0.0,
    total_time: float = 0.0,
    status: SolutionStatus = "valid",
) -> CandidateSolution:
    """手組みの TravelSolution を CandidateSolution に包む。"""
    return CandidateSolution(
        status=status,
        assignments=TravelSolution(
            selected_place_ids=selected_place_ids,
            visit_order=visit_order,
            total_value=total_value,
            total_cost=total_cost,
            total_time=total_time,
        ),
        produced_by=AlgorithmMeta(name="manual", family="optimization", implementation="fixture"),
    )


# ---------------------------------------------------------------------------
# project_scheduling(CPM / RCPSP)
# ---------------------------------------------------------------------------

# 5 タスクの例題。資源無視の CPM: makespan 8、クリティカルパス A -> C -> E、B / D は slack 3。
#   resource_capacity=3 のとき A(res 2)と B(res 1)は t0-2 で共存できるが、C(res 3)は
#   その 4 単位だけで全容量を占め、D(res 1)は C と重なれない。
#     cpm(資源無視)      : makespan 8、ただし C と D が重なり peak 4 > 3 → Verification が invalid
#     priority_list       : 資源 feasible。D を後ろに回して makespan 10(最適ではない)
#     cp_sat              : 資源 feasible な最適 ── makespan 9
_PROJECT_TASKS = [
    ProjectTask(id="A", name="設計", duration=3, resource=2),
    ProjectTask(id="B", name="調達", duration=2, resource=1),
    ProjectTask(id="C", name="実装", duration=4, resource=3),
    ProjectTask(id="D", name="検証", duration=2, resource=1),
    ProjectTask(id="E", name="リリース", duration=1, resource=2),
]
_PROJECT_DEPS = [
    TaskDependency(id="dep_ac", predecessor="A", successor="C"),
    TaskDependency(id="dep_bd", predecessor="B", successor="D"),
    TaskDependency(id="dep_ce", predecessor="C", successor="E"),
    TaskDependency(id="dep_de", predecessor="D", successor="E"),
]


def build_project_problem(
    *,
    resource_capacity: int | None = 3,
    max_makespan: float | None = None,
    forbidden: list[str] | None = None,
) -> OptimizationProblem:
    """例題の Project Manager。CPM / priority_list / CP-SAT / cpm_nx をかける。

    resource_capacity=None にすると純粋 CPM(資源制約なし)。
    """
    constraints: list = []
    if forbidden:
        constraints.append(ForbiddenConstraint(severity="hard", items=forbidden))
    if max_makespan is not None:
        constraints.append(
            NumericBoundConstraint(
                severity="hard", field="makespan", operator="<=", value=max_makespan
            )
        )
    objectives = [Objective(sense="minimize", target="makespan", weight=1.0)]
    if resource_capacity is not None:
        objectives.append(Objective(sense="minimize", target="peak_resource", weight=0.1))
    return OptimizationProblem(
        problem_type="project_scheduling",
        objectives=objectives,
        constraints=constraints,
        data=ProjectData(
            tasks=list(_PROJECT_TASKS),
            dependencies=list(_PROJECT_DEPS),
            resource_capacity=resource_capacity,
        ),
    )


def build_cyclic_project_problem() -> OptimizationProblem:
    """依存が閉路(A -> B -> C -> A)── ProblemValidationService が InfeasibleProblemError。"""
    return OptimizationProblem(
        problem_type="project_scheduling",
        objectives=[Objective(sense="minimize", target="makespan")],
        data=ProjectData(
            tasks=[ProjectTask(id=t, duration=1) for t in ("A", "B", "C")],
            dependencies=[
                TaskDependency(id="d1", predecessor="A", successor="B"),
                TaskDependency(id="d2", predecessor="B", successor="C"),
                TaskDependency(id="d3", predecessor="C", successor="A"),
            ],
        ),
    )


def build_scaled_project_problem(
    n_tasks: int, *, seed: int = 0, resource_capacity: int | None = None
) -> OptimizationProblem:
    """ランダムな DAG(規模別の比較・プロパティテスト用)。

    タスク T0..T(n-1)。依存は i < j の向きにだけ張る(必ず非巡回)。
    `build_scaled_route_problem` と同型 ── seed 固定で RNG 呼び出し順を固定し決定論に。
    """
    if n_tasks < 1:
        raise ValueError(f"n_tasks must be >= 1, got {n_tasks}")
    rng = random.Random(seed)
    tasks = [
        ProjectTask(id=f"T{i}", duration=rng.randint(1, 5), resource=rng.randint(0, 3))
        for i in range(n_tasks)
    ]
    deps: list[TaskDependency] = []
    for j in range(1, n_tasks):
        k = min(rng.randint(1, 2), j)
        for p in rng.sample(range(j), k):
            deps.append(TaskDependency(id=f"d{p}_{j}", predecessor=f"T{p}", successor=f"T{j}"))
    return OptimizationProblem(
        problem_type="project_scheduling",
        objectives=[Objective(sense="minimize", target="makespan")],
        data=ProjectData(tasks=tasks, dependencies=deps, resource_capacity=resource_capacity),
    )


def build_project_solution(
    schedule: list[tuple[str, float, float, float]],
    *,
    critical_path: list[str] | None = None,
    makespan: float | None = None,
    task_order: list[str] | None = None,
    status: SolutionStatus = "valid",
) -> CandidateSolution:
    """手組みの ProjectSolution を包む。schedule = (task_id, start, finish, slack) のリスト。"""
    tasks = [ScheduledTask(task_id=t, start=s, finish=f, slack=sl) for t, s, f, sl in schedule]
    return CandidateSolution(
        status=status,
        assignments=ProjectSolution(
            task_order=task_order or [t for t, *_ in schedule],
            schedule=tasks,
            critical_path=critical_path or [],
            makespan=(
                makespan
                if makespan is not None
                else max((f for _, _, f, _ in schedule), default=0.0)
            ),
        ),
        produced_by=AlgorithmMeta(name="manual", family="scheduling", implementation="fixture"),
    )


# ---------------------------------------------------------------------------
# logistics_planning(CVRP)
# ---------------------------------------------------------------------------

# デポ D + 3 配送先。D-N1=4, D-N2=3, D-N3=6, N1-N2=2, N2-N3=3(全区間無向)。
# 全点対最短距離(Floyd-Warshall): D-N1=4, D-N2=3, D-N3=6, N1-N2=2, N1-N3=5, N2-N3=3。
# 容量 10 に対し demand は P1=4, P2=5, P3=7 ── P1+P2=9 は収まるが、P1+P3=11 / P2+P3=12 は
# 超える。2 台に分けると必ず {P1,P2}(距離 D-N1-N2-D=9)+ {P3}(距離 D-N3-D=12)= 21 になる
# (これ以外の分け方は容量オーバーで作れない)。5 strategy が一致して 21 を出すはずの最小例。
_LOGISTICS_NODES = [
    LogisticsNode(id="D"),
    LogisticsNode(id="N1"),
    LogisticsNode(id="N2"),
    LogisticsNode(id="N3"),
]
_LOGISTICS_SEGMENTS = [
    RoadSegment(id="S_D1", source="D", target="N1", distance=4),
    RoadSegment(id="S_D2", source="D", target="N2", distance=3),
    RoadSegment(id="S_D3", source="D", target="N3", distance=6),
    RoadSegment(id="S_12", source="N1", target="N2", distance=2),
    RoadSegment(id="S_23", source="N2", target="N3", distance=3),
]
_LOGISTICS_VEHICLES = [
    Vehicle(id="V1", capacity_weight=10, capacity_volume=10),
    Vehicle(id="V2", capacity_weight=10, capacity_volume=10),
]
_LOGISTICS_DELIVERIES = [
    DeliveryStop(id="P1", node_id="N1", demand_weight=4, demand_volume=4),
    DeliveryStop(id="P2", node_id="N2", demand_weight=5, demand_volume=5),
    DeliveryStop(id="P3", node_id="N3", demand_weight=7, demand_volume=7),
]


def build_logistics_problem(
    *,
    vehicles: list[Vehicle] | None = None,
    deliveries: list[DeliveryStop] | None = None,
    forbidden: list[str] | None = None,
) -> OptimizationProblem:
    """例題の Logistics Optimizer。knapsack_dp / greedy / branch_and_bound / brute_force /
    pulp_milp をかける(容量の都合で総距離 21・使用台数 2 に一致するはず)。
    """
    constraints: list = []
    if forbidden:
        constraints.append(ForbiddenConstraint(severity="hard", items=forbidden))
    return OptimizationProblem(
        problem_type="logistics_planning",
        objectives=[Objective(sense="minimize", target="total_distance")],
        constraints=constraints,
        data=LogisticsData(
            depot_id="D",
            nodes=list(_LOGISTICS_NODES),
            segments=list(_LOGISTICS_SEGMENTS),
            vehicles=list(vehicles) if vehicles is not None else list(_LOGISTICS_VEHICLES),
            deliveries=list(deliveries) if deliveries is not None else list(_LOGISTICS_DELIVERIES),
        ),
    )


def build_disconnected_logistics_problem() -> OptimizationProblem:
    """配送先の1つ(P2 at N2)がデポと道路で繋がっていない
    (ProblemValidationService が InfeasibleProblemError)。
    """
    return OptimizationProblem(
        problem_type="logistics_planning",
        objectives=[Objective(sense="minimize", target="total_distance")],
        data=LogisticsData(
            depot_id="D",
            nodes=[LogisticsNode(id="D"), LogisticsNode(id="N1"), LogisticsNode(id="N2")],
            segments=[RoadSegment(id="S_D1", source="D", target="N1", distance=5)],
            vehicles=[Vehicle(id="V1", capacity_weight=10, capacity_volume=10)],
            deliveries=[
                DeliveryStop(id="P1", node_id="N1", demand_weight=2, demand_volume=2),
                DeliveryStop(id="P2", node_id="N2", demand_weight=2, demand_volume=2),  # 孤立
            ],
        ),
    )


def build_scaled_logistics_problem(
    n_deliveries: int, *, seed: int = 0, n_vehicles: int | None = None
) -> OptimizationProblem:
    """配送先数を振れるランダム CVRP(規模別の比較・プロパティテスト用)。

    ノードはデポ D を起点に一直線(N1..Nn)+ seed で数本の近道。各ノードに配送先 1 件。
    容量(重量・体積とも 10)に対し demand は 1〜3 に抑えるので、車両を余裕をもって
    (n_deliveries+1)//2 台用意すれば容量面では詰まらない。`build_scaled_project_problem` と
    同型 ── seed 固定で RNG 呼び出し順を固定し決定論を保つ。
    """
    if n_deliveries < 1:
        raise ValueError(f"n_deliveries must be >= 1, got {n_deliveries}")
    rng = random.Random(seed)
    nodes = [
        LogisticsNode(id="D"),
        *(LogisticsNode(id=f"N{i}") for i in range(1, n_deliveries + 1)),
    ]
    segments = [
        RoadSegment(
            id=f"S{i}",
            source="D" if i == 0 else f"N{i}",
            target=f"N{i + 1}",
            distance=rng.randint(1, 5),
        )
        for i in range(n_deliveries)
    ]
    for k in range(max(n_deliveries // 4, 1)):
        a, b = sorted(rng.sample(range(n_deliveries + 1), 2))
        src = "D" if a == 0 else f"N{a}"
        dst = "D" if b == 0 else f"N{b}"
        segments.append(
            RoadSegment(id=f"SC{k}", source=src, target=dst, distance=rng.randint(2, 8))
        )
    deliveries = [
        DeliveryStop(
            id=f"P{i}",
            node_id=f"N{i}",
            demand_weight=rng.randint(1, 3),
            demand_volume=rng.randint(1, 3),
        )
        for i in range(1, n_deliveries + 1)
    ]
    fleet_size = n_vehicles or max(2, (n_deliveries + 1) // 2)
    vehicles = [
        Vehicle(id=f"V{i}", capacity_weight=10, capacity_volume=10) for i in range(fleet_size)
    ]
    return OptimizationProblem(
        problem_type="logistics_planning",
        objectives=[Objective(sense="minimize", target="total_distance")],
        data=LogisticsData(
            depot_id="D", nodes=nodes, segments=segments, vehicles=vehicles, deliveries=deliveries
        ),
    )


def build_logistics_solution(
    routes: list[tuple[str, list[str], float]],
    *,
    total_distance: float | None = None,
    status: SolutionStatus = "valid",
) -> CandidateSolution:
    """手組みの LogisticsSolution を包む。routes = (vehicle_id, stop_ids, distance) のリスト。"""
    vehicle_routes = [VehicleRoute(vehicle_id=v, stop_ids=s, distance=d) for v, s, d in routes]
    return CandidateSolution(
        status=status,
        assignments=LogisticsSolution(
            routes=vehicle_routes,
            total_distance=(
                total_distance if total_distance is not None else sum(d for _, _, d in routes)
            ),
        ),
        produced_by=AlgorithmMeta(name="manual", family="optimization", implementation="fixture"),
    )
