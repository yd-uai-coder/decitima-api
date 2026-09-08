"""Problem / Solution / BenchmarkRun のリポジトリ。

既存 CRUDRepository[ModelType] を継承し、固有クエリだけ足す。
flush() はするが commit() はしない(トランザクション境界は SolveService)。
"""

import uuid
from typing import Any

from app.models.optimization import Problem, Solution, BenchmarkRun
from app.repositories.base import CRUDRepository


class ProblemRepository(CRUDRepository[Problem]):
    model = Problem

    async def create(
        self, *, user_id: uuid.UUID, problem_type: str, payload: dict[str, Any]
    ) -> Problem:
        """問題を1件追加し、flush して id を確定させた状態で返す。"""
        row = Problem(user_id=user_id, problem_type=problem_type, payload=payload)
        self._session.add(row)
        await self._session.flush()
        return row


class SolutionRepository(CRUDRepository[Solution]):
    model = Solution

    async def create(
        self,
        *,
        problem_id: uuid.UUID,
        status: str,
        algorithm_name: str,
        algorithm_implementation: str,
        payload: dict[str, Any],
    ) -> Solution:
        """解を1件追加し、flush して id を確定させた状態で返す。"""
        row = Solution(
            problem_id=problem_id,
            status=status,
            algorithm_name=algorithm_name,
            algorithm_implementation=algorithm_implementation,
            payload=payload,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def list_for_problem(self, problem_id: uuid.UUID) -> list[Solution]:
        """ある問題に紐づく全解を生成日時順で返す(比較 UI 用。Phase 3 で本格利用)。"""
        return await self.list_all(problem_id=problem_id, order_by=Solution.created_at)


class BenchmarkRunRepository(CRUDRepository[BenchmarkRun]):
    model = BenchmarkRun

    async def create(
        self, *, user_id: uuid.UUID, problem_type: str, payload: dict[str, Any]
    ) -> BenchmarkRun:
        """ベンチマーク実行を 1 件追加し、flush して id を確定させた状態で返す。"""
        row = BenchmarkRun(user_id=user_id, problem_type=problem_type, payload=payload)
        self._session.add(row)
        await self._session.flush()
        return row