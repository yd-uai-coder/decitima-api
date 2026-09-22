"""Job の ORM モデル。
ハイブリッド JSONB パターン ── 検索キー(user_id / problem_type / status)だけカラム化。

ジョブキュー(arq)経由で非同期実行される solve の状態を追跡する、problem_type に依存しない
横断的なテーブル(logistics_planning に限らずどの problem_type の重い solve でも使える)。

`JsonB`(JSON/JSONB 切替型)は `models/optimization.py`(Phase 1)のものを再利用する。
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.optimization import JsonB


class Job(Base):
    """非同期実行される solve ジョブ1件。status は queued -> running -> succeeded/failed。"""

    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    # problem_type / status: 一覧・絞り込みに使うので JSON からカラムへ切り出す
    problem_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, index=True, default="queued")
    # payload: {"request": SolveRequest.model_dump(...), "result": CandidateSolution相当|None,
    #           "problem_id": str|None, "solution_id": str|None, "error": str|None}
    payload: Mapped[dict[str, Any]] = mapped_column(JsonB, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
