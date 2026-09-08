"""BenchmarkService ── 1 問題を複数アルゴリズムで解いて実測を横並びにする。

solve と同じく Validation を通す(実際に解くため)。verify と違い「解が条件を満たすか」
ではなく「どのアルゴリズムがどれだけ速い / 最適か」を測る。トランザクション境界は
このサービス(`request.persist` のとき benchmark_runs に 1 行 commit)。

ライフサイクル:
  (a) レート制限        RateLimiter(resource="benchmark")
  (b) Validation        ProblemValidationService.validate(problem)   ← NG は AppError で終了
  (c) アルゴリズム解決   request.algorithms でフィルタ or 全候補。空なら NoAlgorithmError
  (d) 各 strategy:      measure_call(strategy.solve, runs) を to_thread + wait_for で監視
  (e) Verification      SolutionVerificationService.verify(problem, solution)  ← 計測対象外
  (f) quality_ratio     この run 中の最良目的値との比(目的が metrics に無ければ None)
  (g) 永続化            request.persist なら benchmark_runs に 1 行、commit

"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from functools import partial

from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.algorithms.registry import get_strategies
from app.core.config import settings
from app.domain.problems.problem import OptimizationProblem
from app.repositories.optimization import BenchmarkRunRepository
from app.schemas.optimization import BenchmarkEntry, BenchmarkRequest
from app.services.errors import NoAlgorithmError, SolveTimeoutError
from app.services.measurement import measure_call
from app.services.rate_limit import RateLimit, RateLimiter
from app.services.validation import ProblemValidationService
from app.services.verification import SolutionVerificationService


@dataclass(frozen=True)
class BenchmarkOutcome:
    """benchmark の結果。永続化した場合のみ benchmark_id が入る。"""

    entries: list[BenchmarkEntry]
    benchmark_id: uuid.UUID | None


class BenchmarkService:
    """構造化された最適化問題を、アルゴリズム横並びの実測に変える(必要なら永続化する)。"""

    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        self._session = session
        self._runs_repo = BenchmarkRunRepository(session)
        self._validation = ProblemValidationService()
        self._verification = SolutionVerificationService()
        self._rate_limiter = RateLimiter(
            redis,
            resource="benchmark",
            limits=[
                RateLimit(window_seconds=3600, max_requests=settings.BENCHMARK_RATE_LIMIT_PER_HOUR),
                RateLimit(window_seconds=86400, max_requests=settings.BENCHMARK_RATE_LIMIT_PER_DAY),
            ],
        )

    async def run(
        self, *, user_id: uuid.UUID, request: BenchmarkRequest, bypass_rate_limit: bool = False
    ) -> BenchmarkOutcome:
        problem = request.problem

        # (a) レート制限
        if not bypass_rate_limit:
            await self._rate_limiter.enforce(str(user_id))

        # (b) 実際に解くので Validation を通す(verify との違い)
        self._validation.validate(problem)

        # (c) アルゴリズム解決 ── 指定があれば meta.name でフィルタ
        strategies = get_strategies(problem.problem_type)
        if request.algorithms is not None:
            wanted = set(request.algorithms)
            strategies = [s for s in strategies if s.meta.name in wanted]
        if not strategies:
            raise NoAlgorithmError(
                f"no algorithm to benchmark for problem_type={problem.problem_type!r}"
            )

        timeout = request.timeout_seconds or settings.SOLVE_TIMEOUT_SECONDS
        entries: list[BenchmarkEntry] = []
        for strategy in strategies:
            # (d) 計測 ── 同期の measure ループをスレッドに逃がして 1 run あたり timeout を監視
            try:
                solution, measurement = await asyncio.wait_for(
                    asyncio.to_thread(measure_call, partial(strategy.solve, problem), request.runs),
                    timeout,
                )
            except TimeoutError as exc:
                raise SolveTimeoutError(
                    f"benchmark run for {strategy.meta.name!r} exceeded {timeout}s"
                ) from exc

            # (e) 検証(計測対象外)── hard / soft 違反の件数
            verified = self._verification.verify(problem, solution)
            hard = sum(1 for v in verified.violations if v.severity == "hard")
            soft = sum(1 for v in verified.violations if v.severity == "soft")

            ops = solution.metrics.get("_ops")
            entries.append(
                BenchmarkEntry(
                    algorithm=strategy.meta,
                    solution_status=verified.status,
                    metrics=verified.metrics,
                    elapsed_ms_median=measurement.elapsed_ms_median,
                    elapsed_ms_p25=measurement.elapsed_ms_p25,
                    elapsed_ms_p75=measurement.elapsed_ms_p75,
                    peak_memory_kb=measurement.peak_memory_kb,
                    operation_count=int(ops) if ops is not None else None,
                    hard_violations=hard,
                    soft_violations=soft,
                )
            )

        # (f) quality_ratio ── 目的関数値 / この run 中の最良値
        _annotate_quality_ratio(problem, entries)

        # (g) 永続化
        benchmark_id: uuid.UUID | None = None
        if request.persist:
            row = await self._runs_repo.create(
                user_id=user_id,
                problem_type=problem.problem_type,
                payload={
                    "problem": problem.model_dump(mode="json"),
                    "entries": [e.model_dump(mode="json") for e in entries],
                    "runs": request.runs,
                },
            )
            await self._session.commit()
            benchmark_id = row.id

        return BenchmarkOutcome(entries=entries, benchmark_id=benchmark_id)


def _annotate_quality_ratio(problem: OptimizationProblem, entries: list[BenchmarkEntry]) -> None:
    """各 entry に quality_ratio(自分の目的値 / run 中の最良値)を付ける。

    目的が 1 つも無い / valid な解が無い / 目的値が metrics に無い entry は None のまま。
    minimize なら最小値が基準、maximize なら最大値が基準。1.0 = 最良(オラクルと同値)。
    """
    if not problem.objectives:
        return
    objective = problem.objectives[0]
    target = objective.target
    values = [
        e.metrics[target] for e in entries if e.solution_status == "valid" and target in e.metrics
    ]
    if not values:
        return
    best = min(values) if objective.sense == "minimize" else max(values)
    if best == 0:
        return
    for e in entries:
        if e.solution_status == "valid" and target in e.metrics:
            e.quality_ratio = e.metrics[target] / best
