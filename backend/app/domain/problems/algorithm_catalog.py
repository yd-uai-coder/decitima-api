"""registry に登録された全アルゴリズムの静的な1行説明。"""

from __future__ import annotations

ALGORITHM_DESCRIPTIONS: dict[tuple[str, str], str] = {
    ("route_planning", "dijkstra"): "非負辺の単一始点最短路。手実装、既定の選択。",
    ("route_planning", "bellman_ford"): (
        "負辺・負閉路検出に対応する単一始点最短路。負辺があるときの既定。"
    ),
    ("route_planning", "a_star"): (
        "座標があるときのヒューリスティック付き最短路。Dijkstraより探索が絞れる。"
    ),
    ("route_planning", "dijkstra_nx"): (
        "networkx実装のDijkstra。手実装と同じ結果を産業ライブラリで確認する用途。"
    ),
    ("route_planning", "brute_force"): "全経路を列挙する厳密解。小規模のみ現実的、正解オラクル。",
    ("shift_scheduling", "greedy"): "1手ごとに良さそうな割当を選ぶ。高速だが最適性は保証しない。",
    ("shift_scheduling", "backtracking"): (
        "条件を満たさない割当を枝刈りしながら全探索。小規模で最適。"
    ),
    ("shift_scheduling", "branch_and_bound"): (
        "backtrackingに下界推定を加えた枝刈り探索。さらに絞れる。"
    ),
    ("shift_scheduling", "cp_sat"): (
        "OR-Toolsの制約充足ソルバー。実規模向け、厳密解に近い解を返す。"
    ),
    ("network_design", "kruskal"): (
        "辺をコスト順に見て閉路を作らず追加する最小全域木。Union-Findで閉路判定。"
    ),
    ("network_design", "prim"): "頂点を1つずつ広げる最小全域木。密なグラフで有利なことがある。",
    ("network_design", "kruskal_nx"): (
        "networkx実装のMST。手実装と同じ結果を産業ライブラリで確認する用途。"
    ),
    ("travel_planning", "knapsack_dp"): (
        "予算/時間を2次元ナップサックとして解く厳密DP。移動コストを無視した上界。"
    ),
    ("travel_planning", "greedy"): (
        "1手ごとに実際の巡回コストで判定する近似解。必ず予算内に収まる。"
    ),
    ("travel_planning", "brute_force"): (
        "訪問先の組み合わせを全列挙する厳密解。小規模のみ、正解オラクル。"
    ),
    ("project_scheduling", "cpm"): "資源制約を無視したクリティカルパス法。依存関係だけを見た下界。",
    ("project_scheduling", "priority_list"): (
        "後続開始時刻順の貪欲スケジューリング。資源制約下で実行可能な解を返す。"
    ),
    ("project_scheduling", "cp_sat"): (
        "OR-Toolsによる資源制約付きスケジューリング(RCPSP)の厳密解。"
    ),
    ("project_scheduling", "cpm_nx"): (
        "networkx実装のCPM(資源制約なし)。手実装との突き合わせ用オラクル。"
    ),
    ("logistics_planning", "knapsack_dp"): (
        "車両容量を2次元ナップサックとして解く。移動距離を無視した上界。"
    ),
    ("logistics_planning", "greedy"): "1件ずつ実際の巡回距離増分で判定する近似解。",
    ("logistics_planning", "branch_and_bound"): (
        "確定距離を下界にした枝刈り探索。knapsack_dpより厳密、greedyより低速。"
    ),
    ("logistics_planning", "brute_force"): "配送先の割当・巡回順を全列挙する厳密解。小規模のみ。",
    ("logistics_planning", "pulp_milp"): (
        "PuLP(CBC)による使用台数最小化のMILP。距離でなく稼働台数を最適化する。"
    ),
}


def describe_algorithm(problem_type: str, name: str) -> str:
    """静的説明表から1行説明を引く。未登録なら空文字(新規アルゴリズム追加時の書き忘れを
    落とさないための緩いフォールバック ── ハードエラーにはしない)。"""
    return ALGORITHM_DESCRIPTIONS.get((problem_type, name), "")
