# DeciTima samples │ Phase 7
"""作業単位 7-1: Floyd-Warshall プリミティブ。

テスト対象 / ドライバ / スタブ:
- 対象: `floyd_warshall`(純粋関数)
- ドライバ: このテスト関数(`_adj` ヘルパで隣接リストを直接渡す)
- スタブ: 不要 ── 純粋で外部依存を呼ばない(`Phase-0-3.md` の純粋レイヤー)

`build_leg_adjacency`(`adjacency.py`)は 7-4 で追加され、テストは
`test_travel_strategies.py` にある(`TravelData` は 7-3 の葉なので 7-1 では触らない)。
"""

from __future__ import annotations

import math

from app.algorithms.graph.floyd_warshall import floyd_warshall


def _adj(edges: list[tuple[str, str, float]]) -> dict[str, list[tuple[str, str, float]]]:
    """(a, b, w) の無向辺リストから隣接リストを作る(テスト用の素朴ビルダー)。"""
    nodes = {x for a, b, _ in edges for x in (a, b)} # 辺に登場する全ノード id の重複なし集合
    out: dict[str, list[tuple[str, str, float]]] = {n: [] for n in nodes} # ノードに対応した空リストを用意

    # 隣接リストを作る(a:[]とb:[]に隣接ノードとインデックス、重みを追加)
    for i, (a, b, w) in enumerate(edges):
        out[a].append((b, f"e{i}", w)) 
        out[b].append((a, f"e{i}", w))
    return out



def test_direct_edges_and_self_distance() -> None:
    dist = floyd_warshall(_adj([("A", "B", 3.0), ("B", "C", 4.0)]))
    assert dist["A"]["A"] == 0.0 # 自身とのエッジの距離は0.0
    assert dist["A"]["B"] == 3.0
    assert dist["B"]["C"] == 4.0


def test_shortest_goes_through_intermediate() -> None:
    # A-B=10, A-C=1, C-B=1 → A→B の最短は C 経由の 2
    dist = floyd_warshall(_adj([("A", "B", 10.0), ("A", "C", 1.0), ("C", "B", 1.0)]))
    assert dist["A"]["B"] == 2.0  # A-> C -> B なら距離は2.0
    assert dist["B"]["A"] == 2.0  # 無向なので対称


def test_unreachable_is_inf() -> None:
    dist = floyd_warshall(_adj([("A", "B", 1.0), ("C", "D", 1.0)]))  # 2 つの島
    assert dist["A"]["C"] == math.inf # AとCは隣接しないので距離はinf

# 同じノード対 A–B に対して、2 本目の辺(より軽い weight)が登録され、初期化ループが軽い方を採用した
def test_parallel_edges_take_lighter() -> None:
    adj = _adj([("A", "B", 5.0)])
    adj["A"].append(("B", "e_extra", 2.0))
    adj["B"].append(("A", "e_extra", 2.0))
    dist = floyd_warshall(adj)
    assert dist["A"]["B"] == 2.0
