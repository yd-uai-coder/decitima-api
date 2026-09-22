"""Job のリポジトリ。
既存 `CRUDRepository[ModelType]` を継承し、固有クエリだけ足す。flush() はするが
commit() はしない(トランザクション境界はサービス層)。
"""

from __future__ import annotations

import uuid
from typing import Any

from app.models.job import Job
from app.repositories.base import CRUDRepository


class JobRepository(CRUDRepository[Job]):
    model = Job

    async def create(
        self, *, user_id: uuid.UUID, problem_type: str, payload: dict[str, Any]
    ) -> Job:
        """ジョブを1件追加し(status="queued")、flush して id を確定させた状態で返す。"""
        row = Job(user_id=user_id, problem_type=problem_type, payload=payload, status="queued")
        self._session.add(row)
        await self._session.flush()
        return row

    async def update_status(
        self, job_id: uuid.UUID, *, status: str, payload: dict[str, Any] | None = None
    ) -> Job | None:
        """ジョブの status(と任意で payload)を更新する。ワーカーが結果を書き戻すのに使う。"""
        row = await self.get_by_id(job_id)
        if row is None:
            return None
        row.status = status
        if payload is not None:
            row.payload = payload
        await self._session.flush()
        return row
