"""Project Manager の解(葉モジュール)。

スケジュール = タスクの実行順 + 各タスクの開始 / 終了時刻 + クリティカルパス + makespan。
時刻はすべて整数時間単位(t=0 起点)を float で持つ(metrics 辞書 / weighted_sum に合わせる)。

このファイルは兄弟葉を import しない。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel


class ScheduledTask(BaseModel):
    """1 タスクのスケジュール。start / finish は実際に割り当てられた時刻。"""

    task_id: str
    start: float  # 実際の開始時刻(cpm では ES、priority_list / cp_sat では資源都合で後ろ倒しも)
    finish: float  # start + duration
    slack: float  # 総余裕(LS − ES)。0 ならクリティカル。スケジュールの後ろ倒しとは独立


class ProjectSolution(BaseModel):
    """Project Manager の解。実行順・各タスクのスケジュール・クリティカルパス・全体所要。"""

    problem_type: Literal["project_scheduling"] = "project_scheduling"
    task_order: list[str]  # 依存を満たすタスクの実行順(トポロジカル順)
    schedule: list[ScheduledTask]  # 各タスクの start / finish / slack
    critical_path: list[str]  # slack 0 のタスクを起点 → 終点で 1 本に繋いだ列
    makespan: float  # プロジェクト全体の所要時間(= max finish)
