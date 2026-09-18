# DeciTima samples │ 作業単位 15-3
"""`topological_sort`(Kahn法)の大規模入力テスト。

対象: `app.algorithms.graph.topological.topological_sort`。ドライバ: このテスト関数 +
Phase 15-1 の `measure` フィクスチャ。スタブ不要 ── 対象が純粋(副作用なし)で
外部依存を呼ばないため。

DFS版(Phase 8-1〜Phase 15-2 まで)は線形依存チェーンで Python の既定再帰上限(1000)に
達し n≈999 から `RecursionError` を出した(実測は `Phase-15-3.md` 参照)。Kahn法(反復)への
置換後、同じ形状で n をさらに一桁以上大きくしても壊れないことをここで確認する。
"""

import sys

import pytest
from tests.performance.generators import linear_chain_successors

from app.algorithms.graph.topological import topological_sort


@pytest.mark.performance
def test_linear_chain_beyond_recursion_limit_does_not_raise() -> None:
    """Python既定の再帰上限(通常1000)を大きく超える線形チェーンでも例外を出さない。"""
    n = 50_000
    assert n > sys.getrecursionlimit() * 10  # 「大きく超える」ことの根拠を明示

    order = topological_sort(linear_chain_successors(n))

    assert order == [f"T{i}" for i in range(n)]


@pytest.mark.performance
def test_linear_chain_50000_completes_quickly(measure) -> None:
    """O(V+E) なので 50,000 ノードの線形チェーンでも十分高速に完了する。"""
    succ = linear_chain_successors(50_000)

    _, measurement = measure(lambda: topological_sort(succ), 3)

    assert measurement.elapsed_ms_median < 1000  # 1秒未満(反復・単純な入次数計算のため)
