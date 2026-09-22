"""作業単位 10-2: run_simulation(シナリオ実行オーケストレーション)。
作業単位 10-3: sensitivity(二分探索による閾値発見)の配線。

テスト対象 / ドライバ / スタブ:
- 対象: `app.services.simulation.run_simulation`
- ドライバ: このテスト関数(pytest-asyncio)
- スタブ不要 ── Validation / アルゴリズム選択 / 各 strategy.solve / Verification は
  すべて本物(純粋)。Phase 3 BenchmarkService のテストと同じ理由(進行のルール #14)。
"""

from __future__ import annotations

from tests.fixtures.optimization import build_project_problem, build_route_problem

from app.schemas.simulation import ScenarioOverride, SimulationRequest, SensitivitySpec
from app.services.simulation import run_simulation

# --- 10-2: base + scenarios のスイープ -------------------------------------------------


async def test_run_simulation_returns_base_and_a_no_op_scenario_with_matching_metrics() -> None:
    request = SimulationRequest(
        problem=build_route_problem(),
        scenarios=[ScenarioOverride(label="as-is", overrides={})],
    )
    result = await run_simulation(request)

    assert result.base.status == "valid"
    assert result.base.metrics["total_weight"] == 5.0
    assert result.scenarios[0].label == "as-is"
    assert result.scenarios[0].metrics == result.base.metrics  # override 無しなので一致


async def test_run_simulation_reflects_a_real_override_in_the_metrics() -> None:
    request = SimulationRequest(
        problem=build_route_problem(),
        scenarios=[ScenarioOverride(label="goal=D", overrides={"data": {"goal": "D"}})],
    )
    result = await run_simulation(request)

    assert result.scenarios[0].status == "valid"
    assert result.scenarios[0].metrics["total_weight"] != result.base.metrics["total_weight"] # goalが変わったので計算結果も変わる


async def test_run_simulation_marks_broken_override_as_invalid_scenario_without_aborting() -> None:
    """存在しないノードへの override は Validation で弾かれる ── 例外にせず1件だけ記録し、
    他のシナリオは続行する(README「一部が無効でも比較は続く」)。"""
    request = SimulationRequest(
        problem=build_route_problem(),
        scenarios=[
            ScenarioOverride(label="broken", overrides={"data": {"goal": "does-not-exist"}}),
            ScenarioOverride(label="ok", overrides={}),
        ],
    )
    result = await run_simulation(request)

    assert result.scenarios[0].status == "invalid_scenario"
    assert result.scenarios[0].error is not None
    assert result.scenarios[1].status == "valid"  # 1件破綻しても後続は続行する


async def test_run_simulation_pins_the_same_algorithm_across_all_scenarios() -> None:
    """algorithm 未指定でも、base で自動選択された名前を全シナリオに固定する
    (条件だけを変え、アルゴリズム選択の揺れを比較に混ぜないため)。"""
    request = SimulationRequest(
        problem=build_route_problem(),  # 座標無し → 既定は dijkstra
        scenarios=[ScenarioOverride(label="goal=D", overrides={"data": {"goal": "D"}})],
    )
    result = await run_simulation(request)

    assert result.base.algorithm_name == "dijkstra"
    assert result.scenarios[0].algorithm_name == "dijkstra"


# --- 10-3: sensitivity(二分探索による閾値発見) ------------------------------------------


async def test_run_simulation_sensitivity_finds_the_minimal_resource_capacity() -> None:
    """resource_capacity を 3..6 の範囲で二分探索し、makespan が閾値以下になる最小値を
    見つける(3 未満は単独タスクの必要量 3 を満たせず infeasible になるため範囲外)。
    全件スイープの結果と一致することで正しさを確認する(オラクル比較)。"""
    base = build_project_problem(resource_capacity=6)

    # オラクル: 同じ範囲を線形に総当たりして「真の最小値」を求める
    from app.services.simulation import _solve_once, apply_overrides  # noqa: PLC0415

    def _makespan(capacity: int) -> float:
        merged = apply_overrides(base, {"data": {"resource_capacity": capacity}})
        _, metrics, _ = _solve_once(merged, "priority_list")
        return metrics["makespan"]

    values = {c: _makespan(c) for c in range(3, 7)}
    threshold = values[6]  # capacity=6(最も緩い)のときの makespan を目標値にする
    expected = next((c for c in range(3, 7) if values[c] <= threshold), None)

    request = SimulationRequest(
        problem=base,
        algorithm="priority_list",
        scenarios=[ScenarioOverride(label="noop", overrides={})],
        sensitivity=SensitivitySpec(
            field_path="data.resource_capacity",
            low=3,
            high=6,
            target_metric="makespan",
            threshold=threshold,
            mode="at_most",
        ),
    )
    result = await run_simulation(request)

    assert result.sensitivity is not None
    assert result.sensitivity.threshold_value == expected
    # 二分探索が評価した点数は全件スイープ(4点)より少ない(教材の核 ── 複雑さの比較)
    assert len(result.sensitivity.evaluated) <= 4
    # evaluated の値は実際に線形スイープした値と一致する(オラクル比較)
    for capacity, makespan in result.sensitivity.evaluated.items():
        assert makespan == values[capacity]


async def test_run_simulation_sensitivity_returns_none_when_out_of_range() -> None:
    """[low, high] の範囲内に条件を満たす点が無ければ threshold_value は None。"""
    base = build_project_problem(resource_capacity=6)
    request = SimulationRequest(
        problem=base,
        algorithm="priority_list",
        scenarios=[ScenarioOverride(label="noop", overrides={})],
        sensitivity=SensitivitySpec(
            field_path="data.resource_capacity",
            low=3,
            high=6,
            target_metric="makespan",
            threshold=-1.0,  # どの capacity でも満たせない厳しすぎる閾値
            mode="at_most",
        ),
    )
    result = await run_simulation(request)

    assert result.sensitivity is not None
    assert result.sensitivity.threshold_value is None
