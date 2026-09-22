"""作業単位 Critical Path Method(CPM)── プリミティブ。registry には載らない。

依存 DAG と各タスクの所要時間から:
  - 最早開始 / 最早終了(ES / EF)── 前進パス(トポロジカル順)
  - makespan = max EF(資源が無限にあれば何日で終わるか。)
  - 最遅開始 / 最遅終了(LS / LF)── 後退パス(逆トポロジカル順)
  - 余裕 slack = LS − ES(= LF − EF)。0 = クリティカル
  - クリティカルパス(slack 0 のタスクを起点から終点へ 1 本に繋いだ列)

`floyd_warshall` と同じく `ProjectData` を知らない生の dict を取る
ため。呼び出し側(`project_common`)が dict を組む。

計算量: 時間 O(V + E)、空間 O(V)。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from app.algorithms.graph.topological import topological_sort


@dataclass(frozen=True)
class CpmResult:
    """CPM の計算結果。時刻はすべて整数時間単位(t=0 起点)。"""

    order: list[str]  # トポロジカル順
    predecessors: dict[str, list[str]]  # task -> 先行 task 群(priority_list が使う)
    earliest_start: dict[str, int]
    earliest_finish: dict[str, int]
    latest_start: dict[str, int]
    latest_finish: dict[str, int]
    slack: dict[str, int]
    critical_path: list[str]
    makespan: int
    relaxations: int  # 前進 + 後退で辺を緩和した回数(strategy が _ops に使う)


def cpm(durations: Mapping[str, int], successors: Mapping[str, list[str]]) -> CpmResult:
    """所要時間(task -> int)と後続(task -> 後続 task 群)から CPM 一式を計算する。"""
    order = topological_sort(successors)
    predecessors: dict[str, list[str]] = {t: [] for t in order} #タスクに対応する空配列を用意
    for t in order:
        # tと隣接するタスク(ノード)をpredecessors[t]に追加していく。
        for nxt in successors.get(t, []):
            predecessors[nxt].append(t)

    relax = 0

    # 前進パス: ES[t] = max(EF[p] for p in preds)、EF[t] = ES[t] + dur[t]
    es: dict[str, int] = {} # earliest_start：最早開始
    ef: dict[str, int] = {} # earliest_finish：最早終了 --ES + duration`
    for t in order: # タスク(ノード)毎に処理する
        start = 0
        for p in predecessors[t]: # tの隣接タスクごとに計算する
            relax += 1
            start = max(start, ef[p]) # startと隣接タスクの最早終了を比較して遅い方で更新

        # タスクの最早作業期間を更新
        es[t] = start
        ef[t] = start + durations.get(t, 0)

    #タスクの最早終了の最大値が全体所要期間となる
    makespan = max(ef.values(), default=0) 

    # 後退パス: LF[t] = min(LS[s] for s in succs)、LS[t] = LF[t] - dur[t]
    lf: dict[str, int] = {} # latest_start：最遅開始
    ls: dict[str, int] = {} # latest_finish：最遅終了 -- LS + duration
    for t in reversed(order):
        finish = makespan # 全体所要から遡る(makespanを遅らせない範囲での最遅期間計算)
        for s in successors.get(t, []):
            relax += 1
            finish = min(finish, ls[s])

        # タスクの最遅作業期間を更新
        lf[t] = finish
        ls[t] = finish - durations.get(t, 0)

    slack = {t: ls[t] - es[t] for t in order} # 最遅開始 - 最早開始 = 余裕

    # slack[t] == 0
    critical = critical_chain(order, successors, ef, es, {t for t in order if slack[t] == 0})
    return CpmResult(order, predecessors, es, ef, ls, lf, slack, critical, makespan, relax)


def critical_chain(
    order: list[str],
    successors: Mapping[str, list[str]],
    earliest_finish: Mapping[str, int],
    earliest_start: Mapping[str, int],
    critical: set[str],
) -> list[str]:
    """slack 0 のタスクを、EF[p] == ES[s] で「実際に律速している」辺だけ辿って 1 本の列にする。

    複数のクリティカルパスがあるときは後続 id 昇順で単一を返す(`bfs_shortest_path` と同じ方針)。
    `NetworkxCpmStrategy も presentation にこれを再利用する ── CPM の計算自体は別実装。
    """
    # クリティカルパス上にタスクが1つもなければ、クリティカルチェーンも存在しないので [] を返す
    if not critical:
        return []
    
    # 起点 = クリティカルかつ ES 0(先行クリティカルが無い head)。id 昇順で 1 つ
    head = min((t for t in order if t in critical and earliest_start[t] == 0), default=None)
    if head is None:
        return []

    # path(初期状態ではheaadだけが登録された配列)に
    # 以降の行でタスクを加えていく
    path = [head]
    cur = head
    while True:
        # クリティカルパス上の後続タスクを取得してソートする
        nxts = sorted(
            s
            for s in successors.get(cur, [])
            if s in critical and earliest_finish[cur] == earliest_start[s]
        )
        if not nxts:
            break

        cur = nxts[0] # クリティカルパス上の後続タスクの1つ目
        path.append(cur) #パスに追加して次のループへ
    return path
