"""作業単位 6-1: 重み付き和の評価器(domain/objectives/weighted_sum.py)。

対象 = `weighted_sum`(純粋関数)。ドライバ = このテスト関数。スタブ不要 ── 外部依存なし。
"""

from app.domain.objectives.weighted_sum import weighted_sum
from app.domain.problems.problem import Objective

# test_minimize_target_contributes_positivelyとtest_maximize_target_is_sign_flippedで
# 1.totalの算出
# 2.符号反転
# が正常に動作しているかを確認
def test_minimize_target_contributes_positively() -> None:
    objs = [Objective(sense="minimize", target="labor_cost", weight=1.0)]
    assert weighted_sum(objs, {"labor_cost": 20000.0}) == 20000.0


def test_maximize_target_is_sign_flipped() -> None:
    # 「大きいほど良い」を「小さいほど良い」向きにそろえる → 符号反転
    objs = [Objective(sense="maximize", target="day_off_satisfaction", weight=1.0)]
    assert weighted_sum(objs, {"day_off_satisfaction": 0.8}) == -0.8


# metricsが指定されていないからtotalは0.0
def test_missing_metric_is_ignored() -> None:
    objs = [Objective(sense="minimize", target="hour_variance", weight=5.0)]
    assert weighted_sum(objs, {}) == 0.0

# Objectiveとmetricsを複数入れてtotalが正しく計算されることの確認
def test_multi_objective_weighted() -> None:
    objs = [
        Objective(sense="minimize", target="labor_cost", weight=0.7),
        Objective(sense="maximize", target="day_off_satisfaction", weight=0.3),
    ]
    metrics = {"labor_cost": 20000.0, "day_off_satisfaction": 1.0}
    assert weighted_sum(objs, metrics) == 0.7 * 20000.0 - 0.3 * 1.0

# metricsの倍率を変えて計算、結果が正しい事の確認
def test_lower_is_better_ordering() -> None:
    objs = [
        Objective(sense="minimize", target="labor_cost", weight=0.7),
        Objective(sense="maximize", target="day_off_satisfaction", weight=0.3),
    ]
    good = weighted_sum(objs, {"labor_cost": 20000.0, "day_off_satisfaction": 1.0})
    bad = weighted_sum(objs, {"labor_cost": 25000.0, "day_off_satisfaction": 0.0})
    assert good < bad
