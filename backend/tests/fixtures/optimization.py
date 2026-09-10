"""テスト用の問題・解ビルダー。

decitima-api の pyproject は pythonpath=["."] なので `from tests.fixtures.optimization import ...`
で import できる。Phase 2 で shift の解ビルダーと infeasible な shift 問題を追加。
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


def build_scaled_travel_problem(n_places: int, seed: int = 0) -> OptimizationProblem:
    """place を n_places 個ランダム生成した Travel 問題(規模別の analysis / プロパティテスト用)。

    legs は「一直線に繋ぐ + seed で数本の近道」。RNG の呼び出し順を固定して決定論を保つ。
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
            places=places, legs=legs, budget=20, time_budget=20, start="P0", preferences={}
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
