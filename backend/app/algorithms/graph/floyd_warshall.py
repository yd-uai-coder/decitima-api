"""Floyd-Warshall(全点対最短経路)── プリミティブ。registry には載らない。

「どの 2 点の間も、途中に他の点を経由してよいなら最短でいくら?」を一度に全部求める。
Travel Planner が「選んだ訪問地を回る順」を決める前処理に使う。

- 手実装の三重ループ。numpy は使わない(README §8「コア層に数値ライブラリを入れない」)。
  訪問候補は数十のオーダーで、密行列でも O(V^3) は十分に速い。
- 到達不能なペアは `math.inf`。自分自身への距離は 0。
- 距離の対称性は仮定しない(隣接リストが有向でも動く)が、`build_leg_adjacency` は無向。

計算量: 時間 O(V^3)、空間 O(V^2)。
"""

from __future__ import annotations

import math

from app.algorithms.graph.adjacency import Adjacency

# 全点対距離: dist[a][b] = a から b への最短距離(到達不能は math.inf ※正の無限大)
type AllPairs = dict[str, dict[str, float]]


def floyd_warshall(adjacency: Adjacency) -> AllPairs:
    """隣接リスト(nxt, edge_id, weight)から全点対最短距離を返す。

    平行辺(同じ 2 点を結ぶ複数エッジ)は軽い方を採用する。
    """
    nodes = list(adjacency) #全ノードをリスト化

    # distの初期状態はa==bなら距離0、それ以外は距離inf(仮)の辞書
    dist: AllPairs = {a: {b: (0.0 if a == b else math.inf) for b in nodes} for a in nodes}

    for a, edges in adjacency.items():
        for nxt, _edge_id, weight in edges:
            if weight < dist[a][nxt]:  # 平行辺は軽い方
                dist[a][nxt] = weight

    # k を経由してよいことにすると i→j が縮むか、を全 k について
    for k in nodes:
        dk = dist[k]            # kから各ノードへの距離
        for i in nodes:         # 各ノード(出発ノード)単位で操作
            dik = dist[i][k]    # ノードiからノードkへの距離
            if dik == math.inf:
                continue        # i から k に行けないなら k 経由は無意味
            di = dist[i]        # iから各ノードへの距離
            for j in nodes:     # 各ノード(最終ノード)単位で操作
                through_k = dik + dk[j]
                if through_k < di[j]: # kを経由した方が距離が近いなら
                    di[j] = through_k # i-jの距離を更新する
    return dist
