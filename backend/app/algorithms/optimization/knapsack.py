"""Knapsack DP(0/1 ナップサック)── 純粋関数 `knapsack_2d` と、それを使う Travel Strategy。

- `knapsack_2d` … 2 次元容量(ここでは予算 × 時間)の 0/1 ナップサックをボトムアップ DP で解く。
  各アイテムは「使う / 使わない」の 2 択。返すのは選んだアイテムの添字リスト。
- `KnapsackDpTravelStrategy` … place の cost / duration をアイテムの 2 次元「重さ」に、
  好み加重の効用を「価値」にして DP。**移動コストは DP に入れない**(README「Floyd-Warshall は
  前処理」)── 選んでから `travel_common.order_and_cost` が巡回順と移動分を計上する。
  つまり DP の解は「移動を無視した上界」で、実際は移動分だけ予算・時間を食う。この差は
  Verification が hard 判定し、analysis で Greedy と比較する。

計算量: 時間・空間ともに O(n · A · B)(**擬多項式** ── A, B は容量の数値そのものに比例)。
容量が大きいと配列が膨れる ── DP の古典的な注意点として教材で明示する。
"""

from __future__ import annotations

import math

from app.algorithms.optimization.travel_common import (  
    all_pairs,
    parse_travel_problem,
    place_utility,
    travel_solution,
)
from app.domain.problems.problem import OptimizationProblem
from app.domain.solutions.solution import AlgorithmMeta, CandidateSolution

# アイテム: (容量Aの消費, 容量Bの消費, 価値)。A/B は非負整数。
type Item = tuple[int, int, float]

def knapsack_2d(items: list[Item], cap_a: int, cap_b: int) -> list[int]:
    """容量 (cap_a, cap_b) の 0/1 ナップサック。価値最大の添字リストを返す。

    dp[a][b] = 容量 (a, b) までで得られる最大価値。1 アイテムずつ「使わない / 使う」で更新。
    """
    if cap_a < 0 or cap_b < 0:
        return []
    # dp と、その状態に至ったアイテム採否(復元用)
    # (cap_a + 1) × (cap_b + 1) の 2 次元表。+ 1 は「容量 0 の行 / 列」を含めるため(添字 0..cap_a)。
    # 容量がAとBの2つあるため2次元配列となっている。
    dp = [[0.0] * (cap_b + 1) for _ in range(cap_a + 1)]

    # (cap_a + 1) × (cap_b + 1) × len(items) の 3 次元ブール表。使用アイテムをTrueにしていく
    take = [[[False] * len(items) for _ in range(cap_b + 1)] for _ in range(cap_a + 1)]

    for idx, (wa, wb, value) in enumerate(items):
        # a, b を降順に見る ── 同じアイテムを二重に取らない(0/1 の要)
        for a in range(cap_a, wa - 1, -1):      # cap_aから wa-1まで 降順でたどる。
            for b in range(cap_b, wb - 1, -1):  # cap_bから wb-1まで 降順でたどる。
                # dp[a - wa][b - wb] -> Aの残り容量:a - wa、Bの残り容量:bの時の価値(初期値0.0で1回のみ参照する)
                cand = dp[a - wa][b - wb] + value # アイテムを使う場合の価値

                # dp[a][b]はAの容量がa以下でBの容量がb以下にしたときの最大価値(最適解)
                if cand > dp[a][b]: # dp[a][b]:最大価値(暫定)よりアイテムを使う時の価値が高ければ更新
                    dp[a][b] = cand # 最大価値を更新
                    take[a][b] = list(take[a - wa][b - wb]) #アイテムを追加前に同じ残り容量でのbool配列をコピーする
                    take[a][b][idx] = True                  #コピーした配列のアイテムの欄に該当アイテムを追加した旨登録

    chosen = take[cap_a][cap_b] #この更新チャンスはlen(items)回訪れる

    # chosen:最適解のbool配列からtrueのインデックスを取得する
    return [i for i, t in enumerate(chosen) if t]


class KnapsackDpTravelStrategy:
    """place の選択を 2 次元ナップサック DP で解く手実装ストラテジー。"""

    meta = AlgorithmMeta(
        name="knapsack_dp",
        family="optimization",
        implementation="handwritten",
        time_complexity="O(n * budget * time)",
        space_complexity="O(n * budget * time)",
    )

    def solve(self, problem: OptimizationProblem) -> CandidateSolution:
        # problemから(TravelData, 禁止ノード, 必須ノード)を抽出
        data, forbidden, required = parse_travel_problem(problem)

        #TravelDataから費用と時間の隣接リストを作成
        cost_dist, time_dist = all_pairs(data)

        cap_a = math.floor(data.budget) # 総費用を切り下げ
        cap_b = math.floor(data.time_budget) # 総時間を切り下げ
        candidates = [p for p in data.places if p.id not in forbidden]

        items: list[Item] = []
        ids: list[str] = []
        for p in candidates:
            wa = math.ceil(p.cost)  # 消費は切り上げ(容量オーバーを避ける保守側)
            wb = math.ceil(p.duration)
            if wa > cap_a or wb > cap_b:
                continue  # 単体で予算/時間を超える place は DP に入れない
            items.append((wa, wb, place_utility(data, p.id)))
            ids.append(p.id)

        ops = len(items) * (cap_a + 1) * (cap_b + 1)  # DP セルの更新回数(オーダーの目安)
        picked_idx = set(knapsack_2d(items, cap_a, cap_b))
        selected = [ids[i] for i in range(len(ids)) if i in picked_idx]
        selected += [rid for rid in sorted(required) if rid not in selected]  # 必須は後付け
        return travel_solution(data, selected, cost_dist, time_dist, ops, self.meta)
