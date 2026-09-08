"""作業単位 5-1: Union-Find(素集合データ構造)。

対象 = `UnionFind`(純粋クラス)。ドライバ = このテスト関数。スタブ不要 ── 副作用も外部依存も無い。
"""

from app.algorithms.graph.union_find import UnionFind


def test_union_and_connected() -> None:
    uf = UnionFind(["a", "b", "c", "d"])
    # print(uf._parent) -> {'a': 'a', 'b': 'b', 'c': 'c', 'd': 'd'}
    # print("before union")
    # print(uf.find("a")) ->a
    # print(uf.find("b")) ->b
    # print(uf.find("c")) ->c

    # 第二引数側の_parentが第一引数の_parentに書き換わる find("b")-> a
    assert uf.union("a", "b") is True 
    # 第二引数側の_parentが第一引数の_parentに書き換わる
    # ※先の処理でbの_parentは既にaに書き換わっているため  find("c")-> aとなる
    assert uf.union("b", "c") is True
    
    # print("after union")
    # print(uf.find("a")) ->a 
    # print(uf.find("b")) ->a 
    # print(uf.find("c")) ->a 
    assert uf.connected("a", "c")
    assert not uf.connected("a", "d")
    # 既に同じグループ → False(Kruskal がこれで閉路を弾く)
    assert uf.union("a", "c") is False


def test_groups_after_path_compression() -> None:
    uf = UnionFind([str(i) for i in range(6)])
    for a, b in [("0", "1"), ("1", "2"), ("3", "4")]:
        uf.union(a, b) # [["0", "1", "2"],["3", "4"]]で_parentをまとめる
    for x in ("0", "1", "2"):
        uf.find(x)  # 経路圧縮を走らせる
    groups = sorted(sorted(g) for g in uf.groups())
    assert groups == [["0", "1", "2"], ["3", "4"], ["5"]]
    assert uf.group_count() == 3


def test_find_is_stable_and_idempotent() -> None:
    uf = UnionFind(["p", "q", "r"])
    uf.union("p", "q")
    uf.union("q", "r")
    root = uf.find("p")
    # 経路圧縮しても代表は変わらない / connected は対称
    assert uf.find("r") == root
    assert uf.connected("r", "p") == uf.connected("p", "r")
