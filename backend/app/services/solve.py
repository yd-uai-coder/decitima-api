"""SolveService ── solve のユースケース(トランザクション境界。ここで commit する)。

ライフサイクル:
  (a) レート制限          RateLimiter(resource="solve").enforce(user_id)
  (b) Validation          ProblemValidationService.validate(problem)   ← NG は AppError で終了
  (c) アルゴリズム選択     select_strategy(problem, requested)
  (d) 計算                strategy.solve(problem)   ← 純粋。タイムアウトを監視
  (e) Verification        SolutionVerificationService.verify(problem, solution)
  (f) 永続化              persist=True なら Problem / Solution を保存
  (g) commit

例外はここで握らず伝播させる(register_error_handlers が JSON 化)。
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.solutions.solution import CandidateSolution
from app.repositories.optimization import ProblemRepository, SolutionRepository
from app.schemas.optimization import SolveRequest
from app.services.algorithm_selection import select_strategy
from app.services.errors import SolveTimeoutError
from app.services.rate_limit import RateLimit, RateLimiter
from app.services.validation import ProblemValidationService
from app.services.verification import SolutionVerificationService


@dataclass(frozen=True)
class SolveOutcome:
    """solve の結果。永続化した場合のみ problem_id / solution_id が入る。"""

    solution: CandidateSolution
    problem_id: uuid.UUID | None
    solution_id: uuid.UUID | None


class SolveService:
    """構造化された最適化問題を、検証済みの解にして返す(必要なら永続化する)。"""

    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self._session = session
        self._problems = ProblemRepository(session)
        self._solutions = SolutionRepository(session)
        self._validation = ProblemValidationService()
        self._verification = SolutionVerificationService()
        self._rate_limiter = RateLimiter(
            redis,
            resource="solve",
            limits=[
                RateLimit(window_seconds=3600, max_requests=settings.SOLVE_RATE_LIMIT_PER_HOUR),
                RateLimit(window_seconds=86400, max_requests=settings.SOLVE_RATE_LIMIT_PER_DAY),
            ],
        )

    async def solve(
        self,
        *,
        user_id: uuid.UUID,
        request: SolveRequest,
        bypass_rate_limit: bool = False,
    ) -> SolveOutcome:
        problem = request.problem

        # (a) レート制限
        if not bypass_rate_limit:
            await self._rate_limiter.enforce(str(user_id))

        # (b) Validation(NG なら ProblemValidationError / InfeasibleProblemError が飛ぶ)
        self._validation.validate(problem)

        # (c) アルゴリズム選択(該当なしは NoAlgorithmError)
        strategy = select_strategy(problem, request.algorithm)

        # (d) 計算 + タイムアウト監視。solve は同期・純粋なのでスレッドに逃がして wait_for する。
        #     タイムアウトしてもスレッド自体は止められない(MVP の割り切り。Phase-0-5.md §5)。
        timeout = request.timeout_seconds or settings.SOLVE_TIMEOUT_SECONDS
        try:
            raw = await asyncio.wait_for(asyncio.to_thread(strategy.solve, problem), timeout)
        except TimeoutError as exc:
            raise SolveTimeoutError(f"solve exceeded {timeout}s") from exc

        # (e) Verification(hard 違反 → status="invalid"、soft → soft_penalty)
        verified = self._verification.verify(problem, raw)

        # (f) 永続化
        if not request.persist:
            return SolveOutcome(solution=verified, problem_id=None, solution_id=None)

        problem_row = await self._problems.create(
            user_id=user_id,
            problem_type=problem.problem_type,
            payload=problem.model_dump(mode="json"),
        )
        # 解に問題 id を刻んでから保存する(監査・後からの突き合わせ用)
        verified = verified.model_copy(update={"problem_ref": problem_row.id})
        solution_row = await self._solutions.create(
            problem_id=problem_row.id,
            status=verified.status,
            algorithm_name=verified.produced_by.name,
            algorithm_implementation=verified.produced_by.implementation,
            payload=verified.model_dump(mode="json"),
        )

        # (g) commit(トランザクション境界はこのサービス)
        await self._session.commit()

        return SolveOutcome(
            solution=verified, problem_id=problem_row.id, solution_id=solution_row.id
        )
