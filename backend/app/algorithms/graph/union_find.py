"""Union-Find(素集合データ構造 / DSU)── アルゴリズム・プリミティブ。

「この2要素は同じグループか」「2グループを1つにする」を、ならし O(α(n)) ≒ O(1) で行う。
経路圧縮(find のたびに木を平らにする)+ ランク合併(低い木を高い木に繋ぐ)。

registry には載らない。消費者:
- `KruskalStrategy`── 辺を軽い順に見て「閉路を作らない辺」だけ採用する
- 連結性の判定(`connectivity.py`)
"""

from __future__ import annotations

from collections.abc import Iterable


class UnionFind:
    """文字列 id をキーにした素集合。"""

    def __init__(self, elements: Iterable[str]) -> None:
        # _parent[x] = x の親。根は自分自身を指す
        self._parent: dict[str, str] = {e: e for e in elements}
        # _rank[x] = x を根とする木の高さの上界(合併の向きを決めるだけ)
        self._rank: dict[str, int] = dict.fromkeys(self._parent, 0)

    def find(self, x: str) -> str:
        """x が属するグループの代表(根)を返す。道中のノードを根に繋ぎ直す(経路圧縮)。"""
        root = x
        while self._parent[root] != root:
            root = self._parent[root]
        # 経路圧縮: x から root までのノードを全部 root 直下にする
        while self._parent[x] != root:
            self._parent[x], x = root, self._parent[x]
        return root

    def union(self, a: str, b: str) -> bool:
        """a と b のグループを1つにする。すでに同じグループなら False(= 閉路になる辺)。"""
        ra, rb = self.find(a), self.find(b)
        if ra == rb:
            return False
        # 低い木を高い木の下にぶら下げる
        if self._rank[ra] < self._rank[rb]:
            ra, rb = rb, ra
        self._parent[rb] = ra
        if self._rank[ra] == self._rank[rb]:
            self._rank[ra] += 1
        return True

    def connected(self, a: str, b: str) -> bool:
        """a と b が同じグループなら True。"""
        return self.find(a) == self.find(b)

    def group_count(self) -> int:
        """現在のグループ数。全ノードが連結なら 1。"""
        return len({self.find(x) for x in self._parent})

    def groups(self) -> list[set[str]]:
        """グループごとのノード集合。"""
        buckets: dict[str, set[str]] = {}
        for x in self._parent:
            buckets.setdefault(self.find(x), set()).add(x)
        return list(buckets.values())
