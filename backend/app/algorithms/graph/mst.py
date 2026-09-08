"""network_design(最小全域木)ストラテジー共通の足回り。

Kruskal / Prim / networkx は「MST の作り方」だけが違う。共通部分をここに集約する:
  - `parse_network_problem` … data と forbidden / required リンク id を取り出す
  - `resolve_required`       … 必須リンクを検証し、それらで初期化した UnionFind を返す
  - `mst_solution`           … 選んだリンク列(または None)を CandidateSolution に詰める
"""

from __future__ import annotations

from app.algorithms.graph.union_find import UnionFind
from app.domain.problems.network_design import NetworkDesignData, NetworkLink
from app.domain.problems.problem import (
    ForbiddenConstraint,
    OptimizationProblem,
    RequiredInclusionConstraint,
)
from app.domain.solutions.network_design import NetworkDesignSolution
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution


def parse_network_problem(
    problem: OptimizationProblem,
) -> tuple[NetworkDesignData, set[str], set[str]]:
    """(NetworkDesignData, 使えないリンク id, 必須リンク id) を返す。"""
    data = problem.data
    if not isinstance(data, NetworkDesignData):
        raise TypeError(f"expected NetworkDesignData, got {type(data).__name__}")
    forbidden: set[str] = set()
    required: set[str] = set()
    for c in problem.constraints:
        if isinstance(c, ForbiddenConstraint):
            forbidden.update(c.items)
        elif isinstance(c, RequiredInclusionConstraint):
            required.update(c.items)
    return data, forbidden, required


def resolve_required(
    data: NetworkDesignData, forbidden: set[str], required: set[str]
) -> tuple[list[NetworkLink], UnionFind] | None:
    """必須リンクを先に採用し、それらで union 済みの UnionFind を返す。

    必須リンクが「候補に無い / 使えない指定と矛盾 / 必須同士で閉路」なら None(= infeasible)。
    """
    link_by_id = {link.id: link for link in data.links}
    uf = UnionFind(node.id for node in data.nodes)
    picked: list[NetworkLink] = []
    for lid in sorted(required):
        link = link_by_id.get(lid)
        if link is None or lid in forbidden:
            return None
        a, b = link.endpoints
        if not uf.union(a, b):
            return None  # 必須リンクだけで閉路 ── 全域木にならない
        picked.append(link)
    return picked, uf


def mst_solution(
    selected: list[NetworkLink] | None, ops: int | None, meta: AlgorithmMeta
) -> CandidateSolution:
    """選んだリンク列(または None = 非連結)を CandidateSolution に詰める。

    ops=None(ライブラリトラック)なら metrics に "_ops" を入れない。
    """
    ops_metric: dict[str, float] = {} if ops is None else {"_ops": float(ops)}
    if selected is None:
        return CandidateSolution(
            status="infeasible",
            assignments=NetworkDesignSolution(selected_link_ids=[], total_weight=0.0),
            metrics=ops_metric,
            produced_by=meta,
        )
    total = sum(link.weight for link in selected)
    return CandidateSolution(
        status="valid",  # 「hard 制約を満たすか」は Verification が判定する
        assignments=NetworkDesignSolution(
            selected_link_ids=[link.id for link in selected], total_weight=total
        ),
        metrics={"total_weight": total, **ops_metric},
        produced_by=meta,
    )
