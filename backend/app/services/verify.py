"""VerifyService ── POST /api/v1/verify のユースケース。

クライアントが持ち込んだ (問題, 解) のペアを検証だけして返す。永続化しない(DB を触らない)。
solve と違い Semantic Validation は走らせない ── 解けるかではなく「この解が条件を満たすか」
だけを見るため。レート制限だけは、任意ペイロードを受けるので適用する。
"""

from __future__ import annotations

import uuid

from redis.asyncio import Redis

from app.core.config import settings
from app.domain.solutions.solution import CandidateSolution
from app.schemas.optimization import VerifyRequest
from app.services.rate_limit import RateLimit, RateLimiter
from app.services.verification import SolutionVerificationService


class VerifyService:
    """検証サービス。SolutionVerificationService(純粋)を HTTP ユースケースに包む。"""

    def __init__(self, redis: Redis) -> None:
        self._verification = SolutionVerificationService()
        self._rate_limiter = RateLimiter(
            redis,
            resource="verify",
            limits=[RateLimit(3600, settings.VERIFY_RATE_LIMIT_PER_HOUR)],
        )

    async def verify(
        self,
        *,
        user_id: uuid.UUID,
        request: VerifyRequest,
        bypass_rate_limit: bool = False,
    ) -> CandidateSolution:
        if not bypass_rate_limit:
            await self._rate_limiter.enforce(str(user_id))
        return self._verification.verify(request.problem, request.solution)
