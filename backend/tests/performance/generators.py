# DeciTima samples │ 作業単位 15-1
"""大規模入力ジェネレータ ── Phase 15 の性能テスト専用。

既存 `tests/fixtures/optimization.py::build_scaled_*` で作れる形状は再利用する(ここには
書かない)。ここに置くのは、既存フィクスチャでは作れない「最悪ケースの形状」だけ。

3トラック制約(NumPy/SciPy/pandas はコア層に入れない、README §8)を守り、素の Python
(`random` 標準ライブラリ)のみで書く。
"""

from __future__ import annotations


def linear_chain_successors(n: int) -> dict[str, list[str]]:
    """T0 -> T1 -> T2 -> ... -> T(n-1) の一直線 DAG(隣接辞書)を作る。

    `topological_sort` の DFS 実装にとって最も深い再帰を誘発する形 ── 各タスクの後続は
    高々1つなので、枝分かれによる再帰の分散が起きず、深さがそのまま n になる。
    `build_scaled_project_problem`(ランダム DAG)は依存が分散するため、この最悪形状を
    再現できない(Phase-15-3 で実測して確認する)。
    """
    if n < 1:
        raise ValueError(f"n must be >= 1, got {n}")
    return {f"T{i}": [f"T{i + 1}"] if i < n - 1 else [] for i in range(n)}
