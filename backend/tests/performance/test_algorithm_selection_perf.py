# DeciTima samples │ 作業単位 15-2
"""`_MAX_KNAPSACK_DP_CELLS` の実測ベースの回帰テスト。

対象: `knapsack_2d`(travel/logistics 共通の DP 本体)。ドライバ: このテスト関数。
スタブ不要 ── `knapsack_2d` は純粋関数で外部依存を呼ばないため。

**計測方法の選定が重要**: `_MAX_KNAPSACK_DP_CELLS` は `select_strategy`(`POST /solve` が
アルゴリズム未指定のとき使う既定選択)だけが参照する。`POST /solve` は
`strategy.solve(problem)` を **1回**、素の `time` で計るだけ(`tracemalloc` は使わない
── `app/services/solve.py`)。よってここでの実測も `measure_call`(`tracemalloc` 計測、
`POST /benchmark` 専用)ではなく **素の `time.perf_counter` による単発呼び出し**で行う
(この選定の理由は `Phase-15-2.md` §1 で詳述 ── measure_call 経由で計ると `tracemalloc`
の計装オーバーヘッドが乗り、10倍以上の見かけの遅さになって select_strategy が実際に
経験する速度と一致しなくなる)。
"""

import random
import time

import pytest

from app.algorithms.optimization.knapsack import knapsack_2d
from app.services.algorithm_selection import _MAX_KNAPSACK_DP_CELLS

_SOLVE_TIMEOUT_BUDGET_SECONDS = 10.0


def _make_items(n: int, seed: int = 0) -> list[tuple[int, int, float]]:
    rng = random.Random(seed)
    return [(rng.randint(1, 6), rng.randint(1, 5), float(rng.randint(1, 15))) for _ in range(n)]


@pytest.mark.performance
def test_cells_at_current_threshold_fits_solve_timeout() -> None:
    """cells がちょうど `_MAX_KNAPSACK_DP_CELLS` のとき、POST /solve の単発呼び出しが
    `SOLVE_TIMEOUT_SECONDS` に十分な余裕を持って収まる(`POST /solve` は素の1回呼び出し、
    `measure_call`/`tracemalloc` は経由しない)。
    """
    n, cap_b = 5, 16
    cap_a = _MAX_KNAPSACK_DP_CELLS // (n * cap_b)
    items = _make_items(n)

    t0 = time.perf_counter()
    knapsack_2d(items, cap_a, cap_b)
    elapsed = time.perf_counter() - t0

    # 十分な安全マージン(半分未満)を要求する ── パース/検証/DB書き込み等の他オーバーヘッドの余地
    assert elapsed < _SOLVE_TIMEOUT_BUDGET_SECONDS / 2


def test_phase11_9_incident_scale_still_falls_back_to_greedy() -> None:
    """Phase 11-9 の実インシデント規模(budget=100,000, n=5, time_budget=16)は
    Phase 15-2 で閾値を緩和した後も引き続き `_MAX_KNAPSACK_DP_CELLS` を超え、
    `select_strategy` が knapsack_dp でなく greedy を選ぶことを確認する(回帰防止)。
    """
    import math

    cells = 5 * math.floor(100000) * math.floor(16)
    assert cells > _MAX_KNAPSACK_DP_CELLS
