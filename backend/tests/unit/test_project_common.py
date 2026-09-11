"""作業単位 8-4: project_common(parse / successors / durations / 資源プロファイル)。

テスト対象 / ドライバ / スタブ:
- 対象: `parse_project_problem` / `build_successors` / `build_durations` / `resource_profile` /
  `peak_resource`(いずれも純粋)
- ドライバ: このテスト関数 / `build_project_problem` fixture(8-3)、手組みの ScheduledTask
- スタブ: 不要 ── 純粋関数(range_add は Phase 6 の imos プリミティブ)
"""

from __future__ import annotations

import pytest
from tests.fixtures.optimization import build_project_problem, build_route_problem

from app.algorithms.scheduling.project_common import (
    build_durations,
    build_successors,
    parse_project_problem,
    peak_resource,
    resource_profile,
)
from app.domain.problems.project_manager import ProjectData
from app.domain.solutions.project_manager import ScheduledTask


def _pdata(problem) -> ProjectData:  # noqa: ANN001
    assert isinstance(problem.data, ProjectData)
    return problem.data

# ProjectData以外を受け取るとエラーを投げる
def test_parse_rejects_wrong_problem_type() -> None:
    with pytest.raises(TypeError):
        parse_project_problem(build_route_problem())

# ProjectDataからsuccessors_from_edgesの引数に該当する要素を抽出して渡す
def test_build_successors_includes_every_task() -> None:
    succ = build_successors(_pdata(build_project_problem()))
    assert set(succ) == {"A", "B", "C", "D", "E"}
    assert succ["A"] == ["C"]
    assert succ["E"] == []


# ProjectDataからtaskを抽出してdurationの辞書を作成する
def test_build_durations() -> None:
    assert build_durations(_pdata(build_project_problem())) == {
        "A": 3,
        "B": 2,
        "C": 4,
        "D": 2,
        "E": 1,
    }


def test_resource_profile_is_imos_sum_over_intervals() -> None:
    # A: [0,3) res 2、B: [0,2) res 1 → t0,t1 は 3、t2 は 2
    schedule = [
        ScheduledTask(task_id="A", start=0.0, finish=3.0, slack=0.0),
        ScheduledTask(task_id="B", start=0.0, finish=2.0, slack=1.0),
    ]
    profile = resource_profile(schedule, {"A": 2, "B": 1})
    assert profile == [3.0, 3.0, 2.0] # range_add(3, Itr[(0.0, 3.0, 2) , (0.0, 2.0, 1)])
    assert peak_resource(profile) == 3.0


def test_resource_profile_empty_schedule() -> None:
    assert resource_profile([], {}) == []
    assert peak_resource([]) == 0.0
