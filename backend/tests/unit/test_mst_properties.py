"""作業単位 5-2: MST の理論(cut property / cycle property)を実測で確認する。

対象 = 全域木の全列挙 `_all_spanning_trees`(正解オラクル)と、それに対する MST の性質。
ドライバ = このテスト関数。スタブ不要 ── すべて純粋(小グラフの組み合わせ列挙)。

Kruskal / Prim はまだ無い(Phase 5-4)。ここでは「最小全域木とは何か」「なぜ貪欲で解けるか」を
支える 2 つの性質を、小グラフの全数え上げで確かめる。
"""

from itertools import combinations

from tests.fixtures.optimization import build_network_problem

from app.algorithms.graph.connectivity import forms_spanning_tree
from app.domain.problems.network_design import NetworkDesignData, NetworkLink

_Tree = tuple[NetworkLink, ...]


def _links(problem) -> tuple[list[str], list[NetworkLink]]:
    data = problem.data
    assert isinstance(data, NetworkDesignData)
    return [n.id for n in data.nodes], list(data.links)


def _all_spanning_trees(node_ids: list[str], links: list[NetworkLink]) -> list[_Tree]:
    """リンク候補から (V-1) 本を選ぶ組み合わせのうち全域木になるものを全列挙(小グラフ専用)。"""
    need = max(len(node_ids) - 1, 0)
    out: list[_Tree] = []
    for combo in combinations(links, need):
        if forms_spanning_tree(node_ids, [link.endpoints for link in combo]):
            out.append(combo)
    return out


def _weight(tree: _Tree) -> float:
    return sum(link.weight for link in tree)


def _min_trees(node_ids: list[str], links: list[NetworkLink]) -> list[set[str]]:
    """最小重みを達成する全域木のリンク id 集合たち。"""
    trees = _all_spanning_trees(node_ids, links)
    assert trees, "少なくとも 1 本は全域木があるはず"
    best = min(_weight(t) for t in trees)
    return [{link.id for link in t} for t in trees if _weight(t) == best]


def test_enumeration_finds_the_known_mst() -> None:
    node_ids, links = _links(build_network_problem())
    trees = _all_spanning_trees(node_ids, links)
    assert min(_weight(t) for t in trees) == 10.0  # fixture の既知 MST コスト


def test_cut_property_min_crossing_edge_is_in_some_mst() -> None:
    """任意のカット(頂点の 2 分割)で、そのカットを跨ぐ最小重みの辺は、いずれかの MST に含まれる。"""
    node_ids, links = _links(build_network_problem())
    msts = _min_trees(node_ids, links)

    cut_a = {"A"}  # カット {A} vs 残り
    crossing = [e for e in links if (e.endpoints[0] in cut_a) ^ (e.endpoints[1] in cut_a)]
    min_crossing = min(crossing, key=lambda e: e.weight)
    assert any(min_crossing.id in mst for mst in msts)


def test_cycle_property_heaviest_cycle_edge_is_in_no_mst() -> None:
    """任意の閉路で、その閉路の最大重みの辺は、どの MST にも含まれない。"""
    node_ids, links = _links(build_network_problem())
    msts = _min_trees(node_ids, links)

    by_id = {e.id: e for e in links}
    cycle = [by_id["L_ab"], by_id["L_bc"], by_id["L_ac"]]  # A-B-C-A(1 / 2 / 5)
    heaviest = max(cycle, key=lambda e: e.weight)
    assert heaviest.id == "L_ac"
    assert all(heaviest.id not in mst for mst in msts)
