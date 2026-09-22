"""LLM Problem Structuring の機構(純粋関数)── `EXTRACTORS` / `build_overrides` /
`catalog_ids` / `catalog_entries` / `ground_references`。

`EXTRACTORS` は `app.algorithms.registry.REGISTRY` と同型の「problem_type → 実装候補」の
ディスパッチテーブル(1行足すだけで拡張できる)。`build_overrides` は LLM の抽出結果を
`apply_overrides` にそのまま渡せる overrides dict に組み立てる。
`ground_references` は LLM が生成した id 参照(constraints の items、data の単一 id 参照
フィールド)がベース問題のカタログに実在するかを確認する ── 既存 `ProblemValidationService` は
この一致を検査しないため(到達可能性等の計算に使うだけ)、README「LLM 出力は常に信頼しない」
の最後の砦として Phase 11 が追加する。

`services/structuring.py`(サービス。ワークフローを呼ぶ側)から切り出した ── 元は同居しており、
`app.ai.graph.nodes` がこれらを使い、サービスが `app.ai.graph.workflow` を呼ぶため
`workflow -> nodes -> services.structuring -> workflow` の循環 import になっていた。
純粋な機構を葉のモジュールに分ければ、両者はこのモジュールを一方向に import するだけで済む。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.domain.problems.logistics import LogisticsData
from app.domain.problems.network_design import NetworkDesignData
from app.domain.problems.problem import (
    ForbiddenConstraint,
    OptimizationProblem,
    RequiredInclusionConstraint,
)
from app.domain.problems.project_manager import ProjectData
from app.domain.problems.route_planner import RouteData
from app.domain.problems.shift_scheduler import ShiftData
from app.domain.problems.travel_planner import TravelData
from app.schemas.structuring import (
    ExtractedConstraint,
    ExtractedObjective,
    LogisticsDataPatch,
    ProjectDataPatch,
    RouteDataPatch,
    ShiftDataPatch,
    TravelDataPatch,
)

# problem_type ごとの Data Patch スキーマ。新アルゴリズムの追加と同じく既存コードに触れず
# 1 行足すだけで拡張できる(app/algorithms/registry.py::REGISTRY と同型)。
# network_design はトップレベル・スカラーを持たないため None(= LLM を呼ばない)。
EXTRACTORS: dict[str, type[BaseModel] | None] = {
    "route_planning": RouteDataPatch,
    "network_design": None,
    "shift_scheduling": ShiftDataPatch,
    "travel_planning": TravelDataPatch,
    "project_scheduling": ProjectDataPatch,
    "logistics_planning": LogisticsDataPatch,
}


def build_overrides(
    objectives_patch: list[ExtractedObjective],
    constraints_patch: list[ExtractedConstraint],
    data_patch: dict[str, Any],
) -> dict[str, Any]:
    """LLM の抽出結果を `apply_overridesにそのまま渡せる overrides dict に組み立てる。

    objectives_patch が空なら「抽出できなかった」とみなしベースの objectives を維持する
    (overrides に "objectives" キーを含めない)。constraints は空リストも正当な意味
    (制約なし)を持つため、空でも常に "constraints" キーを含める。
    """
    overrides: dict[str, Any] = {
        "constraints": [c.model_dump(exclude_none=True) for c in constraints_patch]
    }
    if objectives_patch:
        overrides["objectives"] = [o.model_dump() for o in objectives_patch]
    if data_patch:
        overrides["data"] = data_patch
    return overrides


def catalog_ids(problem: OptimizationProblem) -> set[str]:
    """problem.data のカタログ(list フィールド)が持つ id を全て集める(ドメインごとに形が
    違うので isinstance で分岐。route はさらに edges も id 参照の対象になる)。"""
    data = problem.data
    if isinstance(data, RouteData):
        return {n.id for n in data.nodes} | {e.id for e in data.edges}
    if isinstance(data, NetworkDesignData):
        return {n.id for n in data.nodes} | {link.id for link in data.links}
    if isinstance(data, ShiftData):
        return {s.id for s in data.staff} | {slot.id for slot in data.slots}
    if isinstance(data, TravelData):
        return {p.id for p in data.places} | {leg.id for leg in data.legs}
    if isinstance(data, ProjectData):
        return {t.id for t in data.tasks} | {d.id for d in data.dependencies}
    if isinstance(data, LogisticsData):
        return (
            {n.id for n in data.nodes}
            | {seg.id for seg in data.segments}
            | {v.id for v in data.vehicles}
            | {d.id for d in data.deliveries}
        )
    return set()


def catalog_entries(problem: OptimizationProblem) -> list[tuple[str, str | None]]:
    """problem.data の「主要な名前付きエンティティ」を (id, name または label) のペアで返す。
    extract_objectives_constraintsのプロンプトに埋め込み、LLM に「id で参照する」
    ことを徹底させるために使う(catalog_ids と違い、edge/leg/segment のような無名の
    関係エンティティは含めない ── 人間が自然言語で名指しするのは大抵ノード側のため)。"""
    data = problem.data
    if isinstance(data, RouteData):
        return [(n.id, n.label) for n in data.nodes]
    if isinstance(data, NetworkDesignData):
        return [(n.id, n.label) for n in data.nodes]
    if isinstance(data, ShiftData):
        return [(s.id, s.name) for s in data.staff]
    if isinstance(data, TravelData):
        return [(p.id, p.name) for p in data.places]
    if isinstance(data, ProjectData):
        return [(t.id, t.name) for t in data.tasks]
    if isinstance(data, LogisticsData):
        return [(n.id, n.label) for n in data.nodes]
    return []


def ground_references(problem: OptimizationProblem, ids: set[str]) -> list[str]:
    """LLM が生成した id 参照がカタログに実在するかを確認する。対象は constraints の
    items(forbidden / required_inclusion)と、data の単一 id 参照フィールド
    (route の start/goal、travel の start、logistics の depot_id)。

    名前(name/label)は対象外 ── downstream の集計(`solution_element_ids` 等)は id で
    突き合わせるため、名前が紛れ込むのは「実在しない id」と同じ害(黙って無視される、または
    誤って missing 扱いになる)を持つ。プロンプト側で「必ず id を使う」ことを徹底し、ここは
    その契約が守られているかの最後の砦として機能する。
    """
    issues: list[str] = []
    for c in problem.constraints:
        if isinstance(c, (RequiredInclusionConstraint, ForbiddenConstraint)):
            issues.extend(
                f"{c.kind} constraint references unknown id {item!r}"
                for item in c.items
                if item not in ids
            )

    data = problem.data
    id_fields: list[tuple[str, str | None]] = []
    if isinstance(data, RouteData):
        id_fields = [("start", data.start), ("goal", data.goal)]
    elif isinstance(data, TravelData):
        id_fields = [("start", data.start)]
    elif isinstance(data, LogisticsData):
        id_fields = [("depot_id", data.depot_id)]
    issues.extend(
        f"data.{field_name} references unknown id {value!r}"
        for field_name, value in id_fields
        if value is not None and value not in ids
    )
    return issues
