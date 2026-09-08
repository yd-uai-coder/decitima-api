"""作業単位 1-6(補助): SolutionVerificationService(route 限定の最小実装)
   作業単位 2-3 / 2-4: SolutionVerificationService(route + shift、全 kind)。
"""

from tests.fixtures.optimization import (
    build_route_problem,
    build_shift_problem,
    build_shift_solution,
)
from app.algorithms.graph.dijkstra import DijkstraStrategy
from app.domain.problems.problem import (
    Objective,
    OptimizationProblem,
    StaffingConstraint,
)
from app.domain.problems.shift_scheduler import ShiftData, ShiftSlot, Staff
from app.domain.solutions.route_planner import RouteSolution
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution
from app.services.verification import SolutionVerificationService

_STRATEGY = DijkstraStrategy()
_VERIFY = SolutionVerificationService()
_META = AlgorithmMeta(name="dijkstra", family="graph", implementation="handwritten")


def _route(node_ids: list[str], edge_ids: list[str], weight: float) -> CandidateSolution:
    return CandidateSolution(
        status="valid",
        assignments=RouteSolution(
            path_node_ids=node_ids, path_edge_ids=edge_ids, total_weight=weight
        ),
        metrics={"total_weight": weight},
        produced_by=_META,
    )

# --- route -----------------------------------------------------------------

# 作業単位 1-6から変更なし(2-3時点で再テスト)
def test_valid_solution_stays_valid_with_no_violations() -> None:
    problem = build_route_problem(forbidden=["e_bd"], required=["C"])
    verified = _VERIFY.verify(problem, _STRATEGY.solve(problem))
    assert verified.status == "valid"
    assert verified.violations == []
    assert verified.metrics["soft_penalty"] == 0.0


# 作業単位 1-6から2-3時点で変更あり
def test_solution_using_forbidden_edge_becomes_invalid() -> None:
    problem = build_route_problem(forbidden=["e_bd"])

    # 作業単位 1-6 でのテスト
    # わざと禁止エッジ e_bd を通る「悪い解」を作る
    # bad = CandidateSolution(
    #     status="valid",
    #     assignments=RouteSolution(
    #         path_node_ids=["A", "B", "D", "E"],
    #         path_edge_ids=["e_ab", "e_bd", "e_de"],
    #         total_weight=5.0,
    #     ),
    #     metrics={"total_weight": 5.0},
    #     produced_by=_META,
    # )
    
    # 作業単位 2-3 でのテスト ※関数化しただけでテスト値は同じ
    bad = _route(["A", "B", "D", "E"], ["e_ab", "e_bd", "e_de"], 5.0)
    verified = _VERIFY.verify(problem, bad)
    assert verified.status == "invalid"
    assert any(v.constraint_kind == "forbidden" for v in verified.violations)


def test_missing_required_node_becomes_invalid() -> None:
    problem = build_route_problem(required=["C"])
    # 作業単位 1-6 でのテスト
    # わざと禁止エッジ e_bd を通る「悪い解」を作る
    # bad = CandidateSolution(
    #     status="valid",
    #     assignments=RouteSolution(
    #         path_node_ids=["A", "B", "D", "E"],
    #         path_edge_ids=["e_ab", "e_bd", "e_de"],
    #         total_weight=5.0,
    #     ),
    #     metrics={"total_weight": 5.0},
    #     produced_by=_META,
    # )
    
    # 作業単位 2-3 でのテスト ※関数化しただけでテスト値は同じ
    bad = _route(["A", "B", "D", "E"], ["e_ab", "e_bd", "e_de"], 5.0)

    verified = _VERIFY.verify(problem, bad)
    assert verified.status == "invalid"
    assert any(v.constraint_kind == "required_inclusion" for v in verified.violations)

# 作業単位 1-6 でのテスト済
# def test_total_weight_mismatch_is_flagged() -> None:
#     problem = build_route_problem()
#     bad = CandidateSolution(
#         status="valid",
#         assignments=RouteSolution(
#             path_node_ids=["A", "B", "D", "E"],
#             path_edge_ids=["e_ab", "e_bd", "e_de"],
#             total_weight=999.0,  # 実際の合計は 5
#         ),
#         produced_by=_META,
#     )
#     verified = _VERIFY.verify(problem, bad)
#     assert verified.status == "invalid"


# 作業単位 2-3 でのテスト
def test_numeric_bound_on_total_weight_makes_invalid() -> None:
    # Dijkstra は上限を無視して最短路(w9)を出す → numeric_bound が invalid にする
    problem = build_route_problem(forbidden=["e_bd"], max_total_weight=8)
    verified = _VERIFY.verify(problem, _STRATEGY.solve(problem))
    assert verified.status == "invalid"
    assert any(v.constraint_kind == "numeric_bound" for v in verified.violations)


# 作業単位 1-6 でのテスト済
def test_verify_does_not_mutate_original() -> None:
    problem = build_route_problem()
    raw = _STRATEGY.solve(problem)
    _VERIFY.verify(problem, raw)
    assert "soft_penalty" not in raw.metrics  # 元の解は書き換えられていない


# 作業単位 1-6 でのテスト済
# どこかの区間が非連結 → 解なし ->statusがinfeasibleが返ること
# STRATEGY.solve(problem)と_VERIFY.verify(problem, raw).statusが一致
def test_infeasible_solution_is_passed_through() -> None:
    problem = build_route_problem(forbidden=["e_ce", "e_de"])
    raw = _STRATEGY.solve(problem)
    assert raw.status == "infeasible"
    assert _VERIFY.verify(problem, raw).status == "infeasible"


# --- shift ---------------------------------------------------------------

_VALID_SHIFT = {"s1": ["tanaka"], "s2": ["sato"], "s3": ["ito"], "s4": ["sato"]}

# すべてのチェックを通過:有効な shift 解
def test_valid_shift_solution_stays_valid_and_computes_metrics() -> None:
    problem = build_shift_problem()
    verified = _VERIFY.verify(problem, build_shift_solution(_VALID_SHIFT))
    assert verified.status == "valid"
    assert verified.metrics["labor_cost"] == 21500.0
    assert verified.metrics["day_off_satisfaction"] == 1.0

# スロット人数不足
def test_understaffed_slot_makes_invalid_via_staffing_constraint() -> None:
    problem = build_shift_problem()
    bad = build_shift_solution({"s1": ["tanaka"], "s2": [], "s3": ["ito"], "s4": ["sato"]})
    verified = _VERIFY.verify(problem, bad)
    assert verified.status == "invalid"
    assert any(v.constraint_kind == "staffing" for v in verified.violations)

# 非 available スロットに割当
def test_assigning_unavailable_staff_makes_invalid() -> None:
    problem = build_shift_problem()
    bad = build_shift_solution({"s1": ["tanaka"], "s2": ["ito"], "s3": ["ito"], "s4": ["sato"]})
    verified = _VERIFY.verify(problem, bad)
    assert verified.status == "invalid"
    assert any("unavailable" in v.message for v in verified.violations)

# 週合計 > `max_weekly_hours
def test_weekly_hours_exceeded_makes_invalid() -> None:
    problem = OptimizationProblem(
        problem_type="shift_scheduling",
        objectives=[Objective(sense="minimize", target="labor_cost")],
        constraints=[StaffingConstraint(severity="hard")],
        data=ShiftData(
            staff=[Staff(id="a", hourly_wage=1000, available_slot_ids=["s1", "s2"])],
            slots=[
                ShiftSlot(
                    id="s1", day="2026-09-01", start_hour=9, end_hour=17, required_headcount=1
                ),
                ShiftSlot(
                    id="s2", day="2026-09-02", start_hour=9, end_hour=17, required_headcount=1
                ),
            ],
            max_weekly_hours=10,
        ),
    )
    verified = _VERIFY.verify(problem, build_shift_solution({"s1": ["a"], "s2": ["a"]}))
    assert verified.status == "invalid"
    assert any("max_weekly_hours" in v.message for v in verified.violations)

# 連続勤務 > `max_consecutive_days`
def test_consecutive_days_exceeded_makes_invalid() -> None:
    problem = OptimizationProblem(
        problem_type="shift_scheduling",
        objectives=[Objective(sense="minimize", target="labor_cost")],
        constraints=[StaffingConstraint(severity="hard")],
        data=ShiftData(
            staff=[Staff(id="a", hourly_wage=1000, available_slot_ids=["s1", "s2"])],
            slots=[
                ShiftSlot(
                    id="s1", day="2026-09-01", start_hour=9, end_hour=13, required_headcount=1
                ),
                ShiftSlot(
                    id="s2", day="2026-09-02", start_hour=9, end_hour=13, required_headcount=1
                ),
            ],
            max_consecutive_days=1,
        ),
    )
    verified = _VERIFY.verify(problem, build_shift_solution({"s1": ["a"], "s2": ["a"]}))
    assert verified.status == "invalid"
    assert any("consecutive" in v.message for v in verified.violations)

# 希望休の日に割当(soft)
def test_requested_day_off_is_soft_and_penalised() -> None:
    problem = build_shift_problem(with_days_off_penalty=True)
    # tanaka を希望休(2026-09-02)の s4 に入れる
    sol = build_shift_solution({"s1": ["tanaka"], "s2": ["sato"], "s3": ["ito"], "s4": ["tanaka"]})
    verified = _VERIFY.verify(problem, sol)
    assert verified.status == "valid"  # soft のみ
    assert verified.metrics["soft_penalty"] == 5.0
    assert verified.metrics["day_off_satisfaction"] == 0.0
    assert any(v.severity == "soft" for v in verified.violations)
