"""Shift Scheduler の問題固有データ(葉モジュール)。"""

from __future__ import annotations

from pydantic import BaseModel, model_validator
from typing import Literal


class RouteNode(BaseModel):
    """経路問題のノード1つ。座標は A* のヒューリスティック用で任意。"""

    id: str
    label: str | None = None
    x: float | None = None
    y: float | None = None


class RouteEdge(BaseModel):
    """経路問題のエッジ1本。weight は距離または所要時間で、非負(Dijkstra の前提)。"""

    id: str
    source: str  # 端点ノードの id
    target: str  # 端点ノードの id
    # weight: Field(ge=0) で「負の重みは Pydantic が弾く」= Input Validation の一部
    # -> Bellman Ford法への対応においてInput Validationでは負の値を許容する
    #   ガードは RouteData 側の model_validator で担う
    weight: float
    directed: bool = False  # False なら source <-> target の双方向


class RouteData(BaseModel):
    """Route Planner の問題固有データ。グラフと始点・終点。"""

    problem_type: Literal["route_planning"] = "route_planning"
    nodes: list[RouteNode]
    edges: list[RouteEdge]
    start: str  # 出発ノードの id
    goal: str  # 目標ノードの id
        # True のときだけ負辺を許可する。負辺は Dijkstra/A* が扱えないので Bellman-Ford 前提。
    allow_negative: bool = False

    @model_validator(mode="after")
    def _guard_negative_weights(self) -> RouteData:
        """allow_negative=False で負辺があれば Input Validation で弾く(従来の ge=0 相当)。"""
        if not self.allow_negative:
            bad = [e.id for e in self.edges if e.weight < 0]
            if bad:
                raise ValueError(
                    f"negative weight on edge(s) {bad}; set allow_negative=True to use Bellman-Ford"
                )
        return self