"""多目的の重み付き和の評価器(domain 層 ── 純粋)。

`OptimizationProblem.objectives`(`Objective` のリスト)と、解の `metrics`(実測値の dict)から
**1 つのスカラー**を作る。探索アルゴリズム(Greedy / Backtracking / B&B)はこのスカラーを
最小化する ── つまり「良い割当ほど小さい」向きにそろえる:

  score = Σ wᵢ · orient(metrics[targetᵢ], senseᵢ)
          orient(v, "minimize") = +v      （小さいほど良い → そのまま）
          orient(v, "maximize") = −v      （大きいほど良い → 符号を反転して「小さいほど良い」に）


**既知の限界(スケール差)**: `labor_cost`(数千〜数万)と `day_off_satisfaction`(0〜1)のように
metric のスケールが桁違いだと、生の重み付き和は大きい方に支配される。実務では各 metric を
基準解比 / min-max で [0,1] に正規化してから足す。本実装は「素の重み付き和」に留め、
呼び出し側が weight でスケールを吸収する前提(fixture の 0.7 / 0.3 もそのつもりの値)。
正規化は将来の改善余地。

registry には載らない ── strategy ではなく「解の採点方法」。`services` を import しない。
"""

from __future__ import annotations

from collections.abc import Iterable

from app.domain.problems.problem import Objective

# metric 名 → 探索スカラーへの寄与。目的が参照する metric が無ければ寄与 0(その目的は無視)。
_MISSING = 0.0


def _orient(value: float, sense: str) -> float:
    """「小さいほど良い」向きにそろえる。maximize は符号反転。"""
    return -value if sense == "maximize" else value


def weighted_sum(objectives: Iterable[Objective], metrics: dict[str, float]) -> float:
    """objectives の重み付き和スカラー(minimize 向き。小さいほど良い割当)。

    - `objectives`: `Objective(sense, target, weight)` のリスト
    - `metrics`: 解の実測値。`Objective.target` をキーに引く
    - 目的が空、または全目的の target が metrics に無ければ 0.0
    """
    total = 0.0
    for obj in objectives:
        value = metrics.get(obj.target, _MISSING)
        total += obj.weight * _orient(value, obj.sense)
    return total
