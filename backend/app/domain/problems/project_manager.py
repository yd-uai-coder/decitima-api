"""Project Manager の問題固有データ(葉モジュール)。設計は README §12.4 / §19 Phase 8。

工程管理 = タスク(所要時間つき)と依存関係(先行 → 後続)から、全体を最短で終える
スケジュールを組む問題。依存は有向辺の列 ── DAG(閉路があれば順序が付かない)。
`resource` / `resource_capacity`では定義だけ。消費は(資源プロファイル /
priority_list / CP-SAT)。

このファイルは兄弟葉を import しない。ユニオンの合成は problem.py が行う。
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class ProjectTask(BaseModel):
    """タスク 1 つ。duration は整数時間単位(日など)。resource は実行中ずっと占有する資源量。"""

    id: str
    name: str | None = None
    duration: int = Field(gt=0)  # 所要時間(> 0)。整数 ── imos の資源グリッドが綺麗に回る
    resource: int = Field(ge=0, default=0)  # 同時占有する資源量(人・機材の数)


class TaskDependency(BaseModel):
    """依存 1 本。predecessor が終わってから successor を始められる(finish-to-start)。"""

    id: str
    predecessor: str
    successor: str


class ProjectData(BaseModel):
    """Project Manager の問題固有データ。タスク・依存・(任意で)資源上限。"""

    problem_type: Literal["project_scheduling"] = "project_scheduling"
    tasks: list[ProjectTask]
    dependencies: list[TaskDependency] = Field(default_factory=list)
    resource_capacity: int | None = None  # 同時に使える資源の上限。None なら資源制約なし

    @model_validator(mode="after")
    def _refs_and_ids(self) -> ProjectData:
        """依存の端点が実在タスクか / id が一意か / 自己依存でないか(Input Validation)。

        閉路検出は「走査」なのでここではやらない ── services/validation.py が
        `topological.has_cycle` で判定する(`Phase-2-2.md` §3「これは計算か? 述語か?」の 4 例目)。
        """
        ids = [t.id for t in self.tasks]
        id_set = set(ids)
        if len(ids) != len(id_set):
            raise ValueError("duplicate task id(s)")
        dep_ids = [d.id for d in self.dependencies]
        if len(dep_ids) != len(set(dep_ids)):
            raise ValueError("duplicate dependency id(s)")
        bad = [
            d.id
            for d in self.dependencies
            if d.predecessor not in id_set or d.successor not in id_set
        ]
        if bad:
            raise ValueError(f"dependency {bad} reference unknown task id(s)")
        self_dep = [d.id for d in self.dependencies if d.predecessor == d.successor]
        if self_dep:
            raise ValueError(f"dependency {self_dep} has predecessor == successor")
        return self
