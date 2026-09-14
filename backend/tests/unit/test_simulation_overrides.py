# DeciTima samples │ Phase 10
"""作業単位 10-1: apply_overrides(汎用 override マージ)。

テスト対象 / ドライバ / スタブ:
- 対象: `app.services.simulation.apply_overrides`(純粋関数)
- ドライバ: このテスト関数(既存 fixture の複数 problem_type を使い、ドメイン非依存であることを
  確認する)
- スタブ不要 ── 対象が純粋(副作用なし)で外部依存を呼ばないため
"""

from __future__ import annotations

import pytest
from tests.fixtures.optimization import build_project_problem, build_route_problem

from app.services.simulation import apply_overrides


def test_apply_overrides_replaces_a_scalar_field_under_data() -> None:
    """route: goal を差し替えるシナリオ(dict のスカラー上書き)。"""
    problem = build_route_problem()
    scenario = apply_overrides(problem, {"data": {"goal": "D"}})
    assert scenario.data.goal == "D"  # type: ignore[union-attr]
    assert problem.data.goal == "E"  # type: ignore[union-attr] ── 元の problem は不変


def test_apply_overrides_works_across_different_problem_types() -> None:
    """override マージはドメイン非依存 ── project_scheduling でも同じ関数で動く。"""
    problem = build_project_problem(resource_capacity=3)
    scenario = apply_overrides(problem, {"data": {"resource_capacity": 1}})
    assert scenario.data.resource_capacity == 1  # type: ignore[union-attr]


def test_apply_overrides_replaces_lists_wholesale_not_element_wise() -> None:
    """RFC 7386 の仕様どおり、list は要素マージせず丸ごと置換される。"""
    problem = build_route_problem()
    # edges を1本だけの list に丸ごと置換する(元は複数本)
    only_edge = problem.data.edges[0].model_dump(mode="json")  # type: ignore[union-attr]
    scenario = apply_overrides(problem, {"data": {"edges": [only_edge]}})
    assert len(scenario.data.edges) == 1  # type: ignore[union-attr]


def test_apply_overrides_rejects_problem_type_change() -> None:
    """ドメインを跨いだシナリオは意味を持たないため、problem_type の変更は禁止する。"""
    problem = build_route_problem()
    with pytest.raises(ValueError, match="problem_type"):
        apply_overrides(problem, {"problem_type": "network_design"})


def test_apply_overrides_raises_validation_error_for_structurally_invalid_override() -> None:
    """存在しないフィールド構造への override は Pydantic の再検証で弾かれる
    (例外にせず invalid_scenario として拾うのは呼び出し側 `run_simulation` の責務、10-2)。"""
    from pydantic import ValidationError

    problem = build_route_problem()
    with pytest.raises(ValidationError):
        # goal を dict に置き換える ── RouteData.goal: str が満たせない
        apply_overrides(problem, {"data": {"goal": {"unexpected": "shape"}}})
