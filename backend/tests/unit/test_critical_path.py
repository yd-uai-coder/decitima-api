# DeciTima samples │ Phase 8
"""作業単位 8-2: Critical Path Method(CPM)プリミティブ。

テスト対象 / ドライバ / スタブ:
- 対象: `cpm`(純粋関数。内部で `topological_sort` を呼ぶ)、`critical_chain`
- ドライバ: このテスト関数(所要時間 dict と後続 dict を直接渡す ── `ProjectData` は 8-3)
- スタブ: 不要 ── 純粋で外部依存を呼ばない

第一テスト = 統合スモーク(`cpm` を既知の DAG で 1 回。写経ミスをこの章で即赤にする。
`ef == es + dur` を末尾で削る・後退パスの初期値を 0 にする等の写経ミスはここで `makespan` /
`critical_path` が狂って落ちる ── Q30 / Q38 の教訓)。
"""

from __future__ import annotations

from app.algorithms.scheduling.critical_path import cpm

# 5 タスクの例題(fixture の build_project_problem と同じ)。
#   A(3) -> C(4) -> E(1) がクリティカルパス。makespan 8。B(2)/D(2) は slack 3。
_DURATIONS = {"A": 3, "B": 2, "C": 4, "D": 2, "E": 1}
_SUCCESSORS = {"A": ["C"], "B": ["D"], "C": ["E"], "D": ["E"], "E": []}


def test_smoke_known_project_makespan_and_critical_path() -> None:
    result = cpm(_DURATIONS, _SUCCESSORS)
    assert result.makespan == 8
    assert result.critical_path == ["A", "C", "E"]
    assert result.earliest_start == {"A": 0, "B": 0, "C": 3, "D": 2, "E": 7}
    assert result.earliest_finish == {'B': 2, 'D': 4, 'A': 3, 'C': 7, 'E': 8}
    assert result.earliest_finish["E"] == 8


def test_slack_is_zero_on_critical_and_positive_elsewhere() -> None:
    result = cpm(_DURATIONS, _SUCCESSORS)
    assert result.slack["A"] == 0 and result.slack["C"] == 0 and result.slack["E"] == 0
    assert result.slack["B"] == 3 and result.slack["D"] == 3


def test_latest_start_and_finish() -> None:
    result = cpm(_DURATIONS, _SUCCESSORS)
    assert result.latest_start["B"] == 3  # B は 3 遅らせても makespan は伸びない
    assert result.latest_finish["A"] == 3


def test_parallel_tasks_no_deps_makespan_is_max_duration() -> None:
    result = cpm({"A": 3, "B": 5, "C": 2}, {"A": [], "B": [], "C": []})
    assert result.makespan == 5
    assert set(result.critical_path) == {"B"}


def test_single_task() -> None:
    result = cpm({"A": 4}, {"A": []})
    assert result.makespan == 4
    assert result.critical_path == ["A"]
    assert result.slack["A"] == 0


def test_empty_project() -> None:
    result = cpm({}, {})
    assert result.makespan == 0
    assert result.order == []
    assert result.critical_path == []


def test_relaxations_counted_for_ops() -> None:
    result = cpm(_DURATIONS, _SUCCESSORS)
    # 4 本の辺 × 前進 + 後退 = 8 回の緩和
    assert result.relaxations == 8


def test_predecessors_exposed_for_priority_list() -> None:
    result = cpm(_DURATIONS, _SUCCESSORS)
    assert sorted(result.predecessors["E"]) == ["C", "D"]
    assert result.predecessors["A"] == []
