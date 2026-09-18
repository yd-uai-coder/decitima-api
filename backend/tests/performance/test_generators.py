# DeciTima samples │ 作業単位 15-1
"""`tests/performance/generators.py` の単体テスト。

対象: `linear_chain_successors`。ドライバ: このテスト関数。
スタブ不要 ── 対象が純粋(副作用なし)で外部依存を呼ばないため。
"""

import pytest
from tests.performance.generators import linear_chain_successors


def test_linear_chain_successors_basic() -> None:
    assert linear_chain_successors(5) == {
        "T0": ["T1"],
        "T1": ["T2"],
        "T2": ["T3"],
        "T3": ["T4"],
        "T4": [],
    }


def test_linear_chain_successors_single_node() -> None:
    assert linear_chain_successors(1) == {"T0": []}


def test_linear_chain_successors_rejects_non_positive() -> None:
    with pytest.raises(ValueError):
        linear_chain_successors(0)
