"""PulpMilpLogisticsStrategy(産業ソルバートラック)── 使用台数を最小化する
ビンパッキング MILP を PuLP(CBC バックエンド)で解く。

手実装 4 strategy(knapsack_dp / greedy / branch_and_bound / brute_force)はいずれも
「総移動距離の最小化」を目的にしていた。PuLP はあえて**別の目的関数**を持つ ──
README §12.5 の評価項目「車両稼働率」に対応する **使用台数の最小化**(古典的なビンパッキング
問題の MILP 定式化)。配送先→車両の割当が決まった後の巡回順序は、既存の
`optimize_waypoint_order`(TSP 近似)にそのまま委譲する ── 経路順序そのものの MILP 化

定式化:
  変数: x[v][d] ∈ {0,1}(配送先 d を車両 v に割り当てるか)、y[v] ∈ {0,1}(車両 v を使うか)
  目的: minimize Σ y[v]
  制約: 各配送先はちょうど1台(Σ_v x[v][d] == 1)/
        使う車両だけが容量を持つ(Σ_d x[v][d]*demand <= capacity[v] * y[v])/ x[v][d] <= y[v]

決定論: CBC はデフォルト設定で同一入力に対し安定した最適値を返す(MILP は解が複数あっても
目的関数値は一意 ── OR-Tools CP-SAT のような `random_seed` 固定は不要。`msg=False` でログを
静音化するだけ)。`_ops` は出さない(仕事はソルバーの中)。


"""

from __future__ import annotations

from typing import cast

import pulp

from app.algorithms.optimization.logistics_common import (
    all_pairs,
    infeasible_logistics_solution,
    logistics_solution,
    parse_logistics_problem,
)
from app.domain.problems.problem import OptimizationProblem
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution


class PulpMilpLogisticsStrategy:
    """PuLP(CBC)でビンパッキング MILP を解く産業ソルバートラック。"""

    meta = AlgorithmMeta(
        name="pulp_milp",
        family="optimization",
        implementation="library:pulp",
        time_complexity="CBC のブランチアンドバウンドに委譲",
        space_complexity="O(vehicles * deliveries)",
    )

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        data, forbidden = parse_logistics_problem(problem)
        dist = all_pairs(data, forbidden)
        vehicles, deliveries = data.vehicles, data.deliveries

        if not deliveries:
            return logistics_solution(data, {}, dist, self.meta, ops=None)

        # pulp.LpProblem は、「最適化問題そのもの」を作るためのクラス
        # オブジェクト名："logistics_bin_packing",
        # 最適化方向：最小化(LpMinimize)
        prob = pulp.LpProblem("logistics_bin_packing", pulp.LpMinimize)

        # 配送先 d を車両 v に割り当てるか
        # xはタプル(v.id, d.id) をkey、LpVariable オブジェクトをvalueに持つ辞書
        # LpVariable オブジェクトは{name(名):"x_{v.id}_{d.id}", cat(カテゴリー):Binary -> 0/1]}
        x = {
            (v.id, d.id): prob.add_variable(f"x_{v.id}_{d.id}", cat="Binary") # cat="Binary -> 
            for v in vehicles
            for d in deliveries
        }

        # その車両を使用するか
        # yはv.id をkey、LpVariable オブジェクトをvalueに持つ辞書
        # LpVariable オブジェクトは{name(名):"y_{v.id}", cat(カテゴリー):Binary -> 0/1]}
        y = {v.id: prob.add_variable(f"y_{v.id}", cat="Binary") for v in vehicles}

        # 目的関数の設定：使用台数の最小化
        # (y_v1 + y_v2 + y_v3)という線形式を作成する※各変数の値はsolveで決定
        prob += pulp.lpSum(y.values())  


        # 制約の設定：各配送先はちょうど1台
        for d in deliveries:
            prob += pulp.lpSum(x[v.id, d.id] for v in vehicles) == 1

        # 制約の設定：車両の重量容量
        for v in vehicles:
            prob += (
                pulp.lpSum(x[v.id, d.id] * d.demand_weight for d in deliveries)
                <= v.capacity_weight * y[v.id] # (* y[v.id])とすることで使わない車両は(* 0)となる
            )
            prob += (
                pulp.lpSum(x[v.id, d.id] * d.demand_volume for d in deliveries)
                <= v.capacity_volume * y[v.id]
            )
            for d in deliveries:
                prob += x[v.id, d.id] <= y[v.id]  # 使わない車両には割り当てない

        # PULP_CBC_CMD は CBCというMILPソルバーをPuLPから呼び出す。
        # msg=False は、CBCの計算ログを表示しない
        # ここで各LpVariableに[0 or 1]が充てられる
        prob.solve(pulp.PULP_CBC_CMD(msg=False))

        if pulp.LpStatus[prob.status] != "Optimal":
            return infeasible_logistics_solution(self.meta)

        assignment: dict[str, list[str]] = {v.id: [] for v in vehicles}
        for v in vehicles:
            for d in deliveries:
                # pulp.value() の型注釈は LpVariable | float | None だが、解いた後の
                # Binary 変数は実際には float(0.0/1.0)を返す ── cast で絞る。
                value = cast("float | None", pulp.value(x[v.id, d.id]))
                if value is not None and value > 0.5:
                    assignment[v.id].append(d.id)

        return logistics_solution(data, assignment, dist, self.meta, ops=None)
