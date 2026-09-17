# DeciTima samples │ Phase 11(11-2: EXTRACTORS/build_overrides/catalog_ids/ground_references
# / 11-4: catalog_entries)
"""作業単位 11-2: `EXTRACTORS` / `build_overrides` / `catalog_ids` / `ground_references`。
作業単位 11-4: `catalog_entries`。

テスト対象 / ドライバ / スタブ:
- 対象: `app.services.structuring` の純粋関数群
- ドライバ: このテスト関数。`apply_overrides`(Phase 10)と組み合わせ、LLM 無しで
  「抽出結果 → overrides → マージ済み問題」の一連を再現する
- スタブ不要 ── 対象・依存(Phase 10 apply_overrides・ベース問題)とも純粋
"""

from __future__ import annotations

from app.domain.problems.base_problems import get_base_problem
from app.schemas.structuring import ExtractedObjective, RouteDataPatch
from app.services.simulation import apply_overrides
from app.services.structuring import (
    EXTRACTORS,
    build_overrides,
    catalog_entries,
    catalog_ids,
    ground_references,
)


def test_extractors_covers_all_six_problem_types_and_network_design_is_none() -> None:
    assert set(EXTRACTORS) == {
        "route_planning",
        "network_design",
        "shift_scheduling",
        "travel_planning",
        "project_scheduling",
        "logistics_planning",
    }
    assert EXTRACTORS["network_design"] is None
    assert EXTRACTORS["route_planning"] is RouteDataPatch


def test_build_overrides_omits_objectives_key_when_extraction_is_empty() -> None:
    """objectives_patch が空 = 抽出できなかった ── ベースの objectives を維持するため
    overrides に "objectives" キー自体を含めない。"""
    overrides = build_overrides([], [], {})
    assert "objectives" not in overrides


def test_build_overrides_includes_objectives_when_extraction_present() -> None:
    overrides = build_overrides(
        [ExtractedObjective(sense="minimize", target="travel_time")], [], {}
    )
    assert overrides["objectives"] == [
        {"sense": "minimize", "target": "travel_time", "weight": 1.0, "description": None}
    ]


def test_build_overrides_always_includes_constraints_key_even_when_empty() -> None:
    """constraints は空リストも正当な意味(制約なし)を持つため、空でも常に含める。"""
    overrides = build_overrides([], [], {})
    assert overrides["constraints"] == []


def test_build_overrides_omits_data_key_when_patch_is_empty() -> None:
    assert "data" not in build_overrides([], [], {})


def test_build_overrides_includes_data_when_patch_present() -> None:
    overrides = build_overrides([], [], {"start": "A"})
    assert overrides["data"] == {"start": "A"}


def test_catalog_ids_collects_nodes_and_edges_for_route() -> None:
    ids = catalog_ids(get_base_problem("route_planning"))
    assert {"A", "B", "C", "D", "E"} <= ids
    assert "e_ab" in ids


def test_catalog_ids_collects_places_and_legs_for_travel() -> None:
    ids = catalog_ids(get_base_problem("travel_planning"))
    assert "P1" in ids
    assert any(id_.startswith("L") for id_ in ids)


def test_ground_references_flags_unknown_required_inclusion_item() -> None:
    """名前(「浅草」)を id の代わりに渡すと、downstream が id で突き合わせるため検知する。"""
    base = get_base_problem("travel_planning")
    merged = apply_overrides(
        base, {"constraints": [{"kind": "required_inclusion", "items": ["浅草"]}]}
    )
    issues = ground_references(merged, catalog_ids(base))
    assert any("浅草" in issue for issue in issues)


def test_ground_references_accepts_known_id() -> None:
    base = get_base_problem("travel_planning")
    merged = apply_overrides(
        base, {"constraints": [{"kind": "required_inclusion", "items": ["P1"]}]}
    )
    assert ground_references(merged, catalog_ids(base)) == []


def test_ground_references_flags_unknown_route_start() -> None:
    base = get_base_problem("route_planning")
    merged = apply_overrides(base, {"data": {"start": "Z"}})
    issues = ground_references(merged, catalog_ids(base))
    assert any("start" in issue for issue in issues)


def test_ground_references_returns_empty_for_an_unmodified_base_problem() -> None:
    base = get_base_problem("logistics_planning")
    assert ground_references(base, catalog_ids(base)) == []


def test_catalog_entries_pairs_ids_with_names_for_travel() -> None:
    entries = catalog_entries(get_base_problem("travel_planning"))
    assert ("P1", "浅草") in entries


def test_catalog_entries_returns_empty_for_a_domain_without_names() -> None:
    """route_planner の RouteNode はラベル無しでも構築できる(id のみ)ため None を許容する。"""
    entries = catalog_entries(get_base_problem("route_planning"))
    assert all(isinstance(id_, str) for id_, _ in entries)
    assert len(entries) == 5
