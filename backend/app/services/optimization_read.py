"""保存済みの問題・解を取り出すサービス。

将来 solve を非同期ジョブ化しても、この取得 API は変わらない。
所有者スコープ: 他ユーザーの問題・解は「存在しない」扱い(NotFoundError → 404)。
"""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.optimization import Problem, Solution, BenchmarkRun
from app.services.errors import NotFoundError


class OptimizationReadService:
    """problems / solutions テーブルの所有者スコープ付き読み出し。"""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_problem(self, problem_id: uuid.UUID, *, user_id: uuid.UUID) -> Problem:
        row = await self._session.get(Problem, problem_id)
        # problem_idでの検索にヒットしないかuser_idが一致しない場合はエラー
        if row is None or row.user_id != user_id:
            raise NotFoundError(f"problem {problem_id} not found")
        return row

    async def get_solution(self, solution_id: uuid.UUID, *, user_id: uuid.UUID) -> Solution:
        # solutions -> problems を結合して所有者を確認する
        stmt = (
            select(Solution)
            .join(Problem, Solution.problem_id == Problem.id)
            .where(Solution.id == solution_id, Problem.user_id == user_id)
        )
        row = (await self._session.execute(stmt)).scalar_one_or_none()
        # 検索結果が0件の場合はエラー
        if row is None:
            raise NotFoundError(f"solution {solution_id} not found")
        return row


    async def list_solutions_for_problem(
        self, problem_id: uuid.UUID, *, user_id: uuid.UUID
    ) -> list[Solution]:
        await self.get_problem(problem_id, user_id=user_id)  # 所有者チェックを兼ねる
        # problem_idが一致するsolutionをリストで取得
        stmt = (
            select(Solution).where(Solution.problem_id == problem_id).order_by(Solution.created_at)
        )
        return list((await self._session.execute(stmt)).scalars().all())


    async def get_benchmark_run(
        self, benchmark_id: uuid.UUID, *, user_id: uuid.UUID
    ) -> BenchmarkRun:
        row = await self._session.get(BenchmarkRun, benchmark_id)
        if row is None or row.user_id != user_id:
            raise NotFoundError(f"benchmark run {benchmark_id} not found")
        return row
