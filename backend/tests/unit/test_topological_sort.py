# DeciTima samples │ Phase 8
"""作業単位 8-1: トポロジカルソート(DFS ベース)プリミティブ。

テスト対象 / ドライバ / スタブ:
- 対象: `topological_sort` / `has_cycle` / `successors_from_edges`(すべて純粋関数)
- ドライバ: このテスト関数(`_succ` ヘルパで (from, to) 辺リストから隣接リストを直接作る)
- スタブ: 不要 ── 純粋で外部依存を呼ばない(`Phase-0-3.md` の純粋レイヤー)

CPM(8-2)/ ProjectData の配線(8-3)はまだ無いので、このテストは生の辞書だけで完結する。
"""

from __future__ import annotations

import pytest

from app.algorithms.graph.topological import (
    CyclicGraphError,
    has_cycle,
    successors_from_edges,
    topological_sort,
)

# node毎の隣接リスト作成
def _succ(nodes: list[str], edges: list[tuple[str, str]]) -> dict[str, list[str]]:
    return successors_from_edges(nodes, edges)


def _respects(order: list[str], edges: list[tuple[str, str]]) -> bool:
    """order の中で、すべての辺 u→v について u が v より前にあるか。"""
    pos = {n: i for i, n in enumerate(order)}
    return all(pos[u] < pos[v] for u, v in edges)


def test_linear_chain_is_sorted_in_order() -> None:
    edges = [("A", "B"), ("B", "C"), ("C", "D")]
    successors = _succ(["A", "B", "C", "D"] , edges) # {'A': ['B'], 'B': ['C'], 'C': ['D'], 'D': []}
    assert topological_sort(successors) == ["A", "B", "C", "D"]


def test_diamond_respects_all_edges() -> None:
    # A -> {B, C} -> D。B と C の相対順は問わないが、全辺が守られていること
    edges = [("A", "B"), ("A", "C"), ("B", "D"), ("C", "D")]
    successors = _succ(["A", "B", "C", "D"] , edges) # == {'A': ['B', 'C'], 'B': ['D'], 'C': ['D'], 'D': []}
    order = topological_sort(successors) # ['A', 'C', 'B', 'D']
    assert _respects(order, edges)
    assert order[0] == "A" and order[-1] == "D"
    assert order[1] == "C" and order[2] == "B"


def test_isolated_and_successor_only_nodes_are_included() -> None:
    # X はどの辺にも現れない孤立ノード、C は successor としてしか現れない
    succ = _succ(["X"], [("A", "B"), ("B", "C")])
    order = topological_sort(succ) # ['X', 'A', 'B', 'C']
    assert set(order) == {"A", "B", "C", "X"}


def test_deterministic_neighbour_order() -> None:
    # 近傍を id 昇順で辿るので同じ DAG は毎回同じ順。ただし DFS 後行順の反転なので
    # 「辞書順」ではない ── 先に潜った B ほど後ろに回る(A -> C -> B)。Kahn 法なら A,B,C。
    succ = _succ(["A", "B", "C"], [("A", "C"), ("A", "B")])
    assert topological_sort(succ) == topological_sort(succ)
    assert topological_sort(succ) == ["A", "C", "B"]
    assert _respects(topological_sort(succ), [("A", "C"), ("A", "B")])


def test_cycle_raises() -> None:
    succ = _succ(["A", "B", "C"], [("A", "B"), ("B", "C"), ("C", "A")])
    # succ == {'A': ['B'], 'B': ['C'], 'C': ['A']} 各nodeの隣接リスト 
    with pytest.raises(CyclicGraphError): # A->B->C->Aでつながる閉路のためエラーをraise
        topological_sort(succ)


def test_has_cycle_reports_bool_without_raising() -> None:
    assert has_cycle(_succ(["A", "B"], [("A", "B"), ("B", "A")])) is True # 閉路のため、CyclicGraphErrorが発生してTrueを返す
    assert has_cycle(_succ(["A", "B", "C"], [("A", "B"), ("A", "C")])) is False # 閉路ではない


def test_self_loop_is_a_cycle() -> None:
    assert has_cycle(_succ(["A"], [("A", "A")])) is True # 閉路（自己ループ)のため、CyclicGraphErrorが発生してTrueを返す
