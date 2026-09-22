"""JobService ── problem_type に依存しない横断サービス。重い solve をジョブキュー
(arq)経由で非同期実行する。既存の同期 `SolveService`とは独立に動き、そちらは
一切変更しない(9-8 の設計方針: ジョブキューは並存する横断インフラ)。

ライフサイクル(投入側。solve / simulate で共通の `_submit`):
  (a) レート制限          RateLimiter(resource=...).enforce(user_id)
  (b) Validation          ProblemValidationService.validate(problem) ← 不正はジョブを作る前に弾く
  (c) Job 行を作成 + commit(status="queued")
  (d) arq へエンキュー ── 実際の実行はワーカープロセスが `app/worker.py` で行う。
      エンキューに失敗したら Job を failed にして(queued のまま孤児にしない)例外を伝播する

`solve_job` 自身は `SolveService.solve` をそのまま呼ぶ(ロジックを重複させない ── 進行のルール #17)。
"""

from __future__ import annotations

import logging
import uuid

from arq import create_pool
from arq.connections import RedisSettings
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.job import Job
from app.repositories.job import JobRepository
from app.schemas.optimization import SolveRequest
from app.schemas.simulation import SimulationRequest
from app.services.errors import NotFoundError
from app.services.rate_limit import RateLimit, RateLimiter
from app.services.validation import ProblemValidationService

logger = logging.getLogger(__name__)


class JobService:
    """solve / simulate をジョブとして投入し、状態をポーリングできるようにする。"""

    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self._session = session
        self._jobs = JobRepository(session)
        self._validation = ProblemValidationService()
        self._rate_limiter = RateLimiter(
            redis,
            resource="job_submit",
            limits=[
                RateLimit(
                    window_seconds=3600, max_requests=settings.JOB_SUBMIT_RATE_LIMIT_PER_HOUR
                ),
                RateLimit(
                    window_seconds=86400, max_requests=settings.JOB_SUBMIT_RATE_LIMIT_PER_DAY
                ),
            ],
        )
        self._simulate_rate_limiter = RateLimiter(
            redis,
            resource="simulate_submit",
            limits=[
                RateLimit(
                    window_seconds=3600,
                    max_requests=settings.SIMULATE_SUBMIT_RATE_LIMIT_PER_HOUR,
                ),
                RateLimit(
                    window_seconds=86400,
                    max_requests=settings.SIMULATE_SUBMIT_RATE_LIMIT_PER_DAY,
                ),
            ],
        )

    async def enqueue(
        self,
        *,
        user_id: uuid.UUID,
        request: SolveRequest,
        bypass_rate_limit: bool = False,
    ) -> Job:
        """solve ジョブを作成して arq に投入する。solve 自体はここでは実行しない。"""
        return await self._submit(
            function="solve_job",
            limiter=self._rate_limiter,
            user_id=user_id,
            request=request,
            bypass_rate_limit=bypass_rate_limit,
        )

    async def enqueue_simulation(
        self,
        *,
        user_id: uuid.UUID,
        request: SimulationRequest,
        bypass_rate_limit: bool = False,
    ) -> Job:
        """simulate ジョブを作成して arq に投入する。`enqueue` と同じ流れで、
        レート制限だけ別枠、実行は `simulate_job`(`app/worker.py`)に委ねる。
        Validation は base problem だけ(各シナリオの検証は実行時に run_simulation が行う)。"""
        return await self._submit(
            function="simulate_job",
            limiter=self._simulate_rate_limiter,
            user_id=user_id,
            request=request,
            bypass_rate_limit=bypass_rate_limit,
        )

    async def get_status(self, job_id: uuid.UUID) -> Job | None:
        """ジョブの現在の行を返す(見つからなければ None)。所有者は見ない。"""
        return await self._jobs.get_by_id(job_id)

    async def get_for_user(
        self, job_id: uuid.UUID, *, user_id: uuid.UUID, is_superuser: bool = False
    ) -> Job:
        """所有者スコープ付きでジョブを返す。他人のジョブ・存在しないジョブは区別せず
        NotFoundError(404)にして、id の存在有無を漏らさない(`OptimizationReadService` と同じ方針)。
        superuser は他人のジョブも読める。"""
        job = await self._jobs.get_by_id(job_id)
        if job is None or (job.user_id != user_id and not is_superuser):
            raise NotFoundError(f"job {job_id} not found")
        return job

    async def _submit(
        self,
        *,
        function: str,
        limiter: RateLimiter,
        user_id: uuid.UUID,
        request: SolveRequest | SimulationRequest,
        bypass_rate_limit: bool,
    ) -> Job:
        """`enqueue` / `enqueue_simulation` の共通本体(function = arq に登録した関数名)。"""
        # (a) レート制限
        if not bypass_rate_limit:
            await limiter.enforce(str(user_id))

        # (b) Validation(NG なら ProblemValidationError / InfeasibleProblemError が飛ぶ ──
        #     ジョブを作る前に弾くので、キューに積んでからワーカーが失敗する無駄を避けられる)
        self._validation.validate(request.problem)

        # (c) Job 行を作成して確定させる
        job = await self._jobs.create(
            user_id=user_id,
            problem_type=request.problem.problem_type,
            payload={"request": request.model_dump(mode="json"), "result": None, "error": None},
        )
        await self._session.commit()

        # (d) arq へエンキュー。_job_id を Job.id と揃えておく ── arq 側のジョブ id と
        #     こちらの Job 行の id が常に一致するので、後から arq 側の状態を突き合わせやすい
        #     (副作用として arq の一意性保証も効き、同じ Job.id での二重投入を防げる)。
        #     プールはここで作って使い終えたら閉じる(教材としての単純さ優先 ── 本番では
        #     プロセス起動時に1度だけ作って使い回す最適化の余地がある)。
        try:
            pool = await create_pool(RedisSettings.from_dsn(settings.REDIS_URL))
            try:
                await pool.enqueue_job(function, str(job.id), _job_id=str(job.id))
            finally:
                await pool.aclose()
        except Exception:
            # (c) で commit 済みなので、何もしないと誰も処理しない queued 行が残り続ける。
            # failed に倒して(利用者向けの固定メッセージ。詳細はログ)から元の例外を伝播する。
            logger.exception("failed to enqueue %s for job %s", function, job.id)
            await self._jobs.update_status(
                job.id,
                status="failed",
                payload={**job.payload, "error": "failed to enqueue job"},
            )
            await self._session.commit()
            raise

        return job
