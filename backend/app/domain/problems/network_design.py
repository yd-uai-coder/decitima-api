from __future__ import annotations

from pydantic import BaseModel
from typing import Literal


class NetworkNode(BaseModel):
    """Network Designer（MST）の拠点1つ。"""

    id: str
    label: str | None = None


class NetworkLink(BaseModel):
    """敷設可能なリンク1本。無向で、weight は敷設コスト / 距離。"""

    id: str
    endpoints: tuple[str, str]        # 接続する 2 ノードの id
    weight: float


class NetworkDesignData(BaseModel):
    """Network Designer の問題固有データ。拠点と敷設可能なリンク候補（Phase 4 / MST）。"""

    problem_type: Literal["network_design"] = "network_design"
    nodes: list[NetworkNode]
    links: list[NetworkLink]
