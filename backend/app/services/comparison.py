"""`ComparisonService` ── README §14「LLM vs Algorithm Comparison」の実装。

同一の `OptimizationProblem` を
  (a) 既定選択(`select_strategy`)の Algorithm 経路 ── 1回、決定論的
  (b) LLM Only 経路(`app/algorithms/llm/` の `LlmOnly*Strategy`)── `llm_runs` 回、非決定論的
の両方で解き、`SolutionVerificationService` で同じ基準で検証した上で6軸を集計する。

LangGraph は使わない(Phase 9/10/12/13 と同じ判断 ── DB 読み取りなし、直線フロー)。
Structuring/Recommendation/Explanation と異なり、**測定そのものにはリトライもグレースフル
デグレードも行わない**(LLM Only の生の信頼性を測ることが目的のため、失敗を隠すと計測が歪む)。
一方、末尾のナレーション生成(6.のみ)は Phase 12/13 と同じグレースフルデグレードを行う ──
「数値の集計」と「その説明文」で信頼性要件が違うことをそのまま設計に反映している。

永続化はしない
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
import uuid
from statistics import median
from typing import cast

from langchain_core.messages import HumanMessage
from redis.asyncio import Redis

from app.ai.llm.gemini import get_gemini_llm
from app.algorithms.base import AlgorithmStrategy
from app.algorithms.llm.logistics_llm import LlmOnlyLogisticsStrategy
from app.algorithms.llm.network_llm import LlmOnlyNetworkStrategy
from app.algorithms.llm.project_llm import LlmOnlyProjectStrategy
from app.algorithms.llm.route_llm import LlmOnlyRouteStrategy
from app.algorithms.llm.shift_llm import LlmOnlyShiftStrategy
from app.algorithms.llm.travel_llm import LlmOnlyTravelStrategy
from app.core.config import settings
from app.domain.problems.problem import OptimizationProblem
from app.domain.solutions.solution import CandidateSolution
from app.schemas.comparison import (
    ComparisonMetrics,
    ComparisonNarrative,
    ComparisonRequest,
    ComparisonResponse,
    RunOutcome,
)
from app.services.algorithm_selection import select_strategy
from app.services.errors import NoAlgorithmError
from app.services.rate_limit import RateLimit, RateLimiter
from app.services.validation import ProblemValidationService
from app.services.verification import SolutionVerificationService

logger = logging.getLogger(__name__)

# problem_type ごとの LLM Only 戦略。REGISTRY(app/algorithms/registry.py)には登録しない
# ── 本番 /solve の既定選択に一切影響させない、比較専用のインスタンス。
_LLM_ONLY_STRATEGIES: dict[str, AlgorithmStrategy] = {
    "route_planning": LlmOnlyRouteStrategy(),
    "network_design": LlmOnlyNetworkStrategy(),
    "shift_scheduling": LlmOnlyShiftStrategy(),
    "travel_planning": LlmOnlyTravelStrategy(),
    "project_scheduling": LlmOnlyProjectStrategy(),
    "logistics_planning": LlmOnlyLogisticsStrategy(),
}


class ComparisonService:
    """POST /api/v1/compare のユースケース。永続化しない。"""

    def __init__(self, redis: Redis) -> None:
        # redis: レート制限カウンタの保存に使う非同期Redisクライアント
        self._validation = ProblemValidationService()
        self._verification = SolutionVerificationService()
        self._rate_limiter = RateLimiter(
            redis,
            resource="compare",
            limits=[
                RateLimit(window_seconds=3600, max_requests=settings.COMPARE_RATE_LIMIT_PER_HOUR),
                RateLimit(window_seconds=86400, max_requests=settings.COMPARE_RATE_LIMIT_PER_DAY),
            ],
        )

    async def compare(
        self,
        *,
        user_id: uuid.UUID,
        request: ComparisonRequest,
        bypass_rate_limit: bool = False,
    ) -> ComparisonResponse:
        if not bypass_rate_limit:
            await self._rate_limiter.enforce(str(user_id))

        problem = request.problem
        # 実際に両経路で解くので Validation を通す(solve/benchmark と同じ)
        self._validation.validate(problem)

        llm_strategy = _LLM_ONLY_STRATEGIES.get(problem.problem_type)
        if llm_strategy is None:
            raise NoAlgorithmError(f"no llm_only strategy for {problem.problem_type!r}")

        algorithm = select_strategy(problem, request.algorithm)
        algorithm_result = await self._run_once(algorithm, problem)
        # llm_runs 回、直列に再実行する(再現性・エラー率は「N回のばらつき」そのものが指標)
        llm_results = [await self._run_once(llm_strategy, problem) for _ in range(request.llm_runs)]

        metrics = _aggregate(problem, algorithm_result, llm_results)
        narrative = await self._narrate(problem, algorithm, algorithm_result, llm_results, metrics)

        return ComparisonResponse(
            problem_type=problem.problem_type,
            algorithm_used=algorithm.meta,
            algorithm_result=algorithm_result,
            llm_results=llm_results,
            metrics=metrics,
            narrative=narrative,
        )

    async def _run_once(
        self, strategy: AlgorithmStrategy, problem: OptimizationProblem
    ) -> RunOutcome:
        """strategy.solve を1回実行し、検証つきで RunOutcome にする。

        例外はここで捕捉するが、Structuring 等と違って握りつぶして代替結果を返したりは
        しない ── 「エラー率」として数えるためにそのまま記録する。
        """
        start = time.perf_counter()
        try:
            solution = await asyncio.wait_for(
                asyncio.to_thread(strategy.solve, problem), settings.SOLVE_TIMEOUT_SECONDS
            )
        except Exception as exc:  # noqa: BLE001 ── 生の信頼性を測る対象。記録して先へ進む
            elapsed_ms = (time.perf_counter() - start) * 1000.0
            logger.warning("comparison run failed for %s: %r", strategy.meta.name, exc)
            return RunOutcome(status=None, elapsed_ms=elapsed_ms, error=repr(exc))

        elapsed_ms = (time.perf_counter() - start) * 1000.0
        verified = self._verification.verify(problem, solution)
        hard = sum(1 for v in verified.violations if v.severity == "hard")
        soft = sum(1 for v in verified.violations if v.severity == "soft")
        return RunOutcome(
            status=verified.status,
            metrics=_objective_metrics(problem, verified),
            hard_violations=hard,
            soft_violations=soft,
            elapsed_ms=elapsed_ms,
            structure_hash=_structure_hash(verified),
        )

    async def _narrate(
        self,
        problem: OptimizationProblem,
        algorithm: AlgorithmStrategy,
        algorithm_result: RunOutcome,
        llm_results: list[RunOutcome],
        metrics: ComparisonMetrics,
    ) -> ComparisonNarrative:
        prompt = _narrate_prompt(problem, algorithm, algorithm_result, llm_results, metrics)
        try:
            llm = get_gemini_llm(temperature=0).with_structured_output(ComparisonNarrative)
            # ainvoke: LangGraph を介さない素の async 関数なので自分で非同期呼び出しする
            # (Phase 12/13 と同じ判断)
            result = await llm.ainvoke([HumanMessage(content=prompt)])
            return cast(ComparisonNarrative, result)
        except Exception as exc:  # noqa: BLE001 ── ナレーションは補助。失敗しても数値結果は返す
            logger.warning("comparison narrative LLM call failed: %r", exc)
            return _fallback_narrative(metrics)


def _structure_hash(solution: CandidateSolution) -> str:
    """解の構造(assignments)を短いハッシュに要約する(再現性の集計用)。"""
    payload = json.dumps(solution.assignments.model_dump(mode="json"), sort_keys=True)
    return hashlib.sha256(payload.encode()).hexdigest()[:12]


def _objective_metrics(
    problem: OptimizationProblem, solution: CandidateSolution
) -> dict[str, float]:
    """目的の対象値を metrics に補う。

    route/network/travel/project/logistics は目的の対象(total_weight/total_value/makespan/
    total_distance)が `solution.assignments` 側のフィールドにあり、`verify()` の
    `metrics` には乗らない(shift だけは `structural_verify` が `assignment_metrics()` で
    labor_cost 等を既に `metrics` に積んでいる)。ここで両ケースを吸収して
    `metrics[objective.target]` を必ず引けるようにする(「最適性」の集計が全ドメインで動くため)。
    """
    resolved = dict(solution.metrics)
    for o in problem.objectives:
        if o.target in resolved:
            continue
        value = getattr(solution.assignments, o.target, None)
        if isinstance(value, int | float):
            resolved[o.target] = float(value)
    return resolved


def _aggregate(
    problem: OptimizationProblem,
    algorithm_result: RunOutcome,
    llm_results: list[RunOutcome],
) -> ComparisonMetrics:
    """README §14 の6評価軸のうち数値化できる5軸を集計する(6軸目「検証可能性」は
    `_narrate` の verifiability_note で定性的に扱う)。"""
    attempts = len(llm_results)
    ok = [r for r in llm_results if r.error is None]
    valid = [r for r in ok if r.status == "valid"]

    target = problem.objectives[0].target if problem.objectives else None
    sense = problem.objectives[0].sense if problem.objectives else "minimize"
    algo_value = algorithm_result.metrics.get(target) if target else None

    # ratio: 1.0 = Algorithm と同等。値が大きいほど LLM が劣ることを表す(algo_value が
    # 0 または未知なら比較不能なので None のまま)。
    ratios: list[float] = []
    if target is not None and algo_value not in (None, 0):
        for r in valid:
            v = r.metrics.get(target)
            if v is None:
                continue
            if sense == "minimize":
                ratios.append(v / algo_value)
            elif v != 0:
                ratios.append(algo_value / v)

    distinct = len({r.structure_hash for r in ok if r.structure_hash is not None})

    return ComparisonMetrics(
        constraint_compliance_rate_algorithm=1.0 if algorithm_result.status == "valid" else 0.0,
        # 分母は「成功した試行数」(ok)── 例外で落ちた回は「制約を破った」のではなく
        # 「解自体を出せなかった」ので、遵守率でなく error_rate_llm 側に反映する。
        constraint_compliance_rate_llm=(len(valid) / len(ok)) if ok else 0.0,
        optimality_avg_quality_ratio_llm=(sum(ratios) / len(ratios)) if ratios else None,
        reproducibility_distinct_solutions_llm=distinct,
        execution_time_ms_algorithm=algorithm_result.elapsed_ms,
        execution_time_ms_llm_median=(
            median([r.elapsed_ms for r in llm_results]) if llm_results else 0.0
        ),
        error_rate_llm=((attempts - len(ok)) / attempts) if attempts else 0.0,
    )


def _narrate_prompt(
    problem: OptimizationProblem,
    algorithm: AlgorithmStrategy,
    algorithm_result: RunOutcome,
    llm_results: list[RunOutcome],
    metrics: ComparisonMetrics,
) -> str:
    """比較結果の要約文を作らせるプロンプト。数値は検証済みの事実としてそのまま渡し、
    LLM には narrate(説明)だけをさせる(README「LLM に最適解を計算させない」の徹底、
    Phase 13 `_explain_prompt` と同じ方針)。"""
    llm_statuses = [r.status or f"error: {r.error}" for r in llm_results]
    return (
        f"次の最適化問題(problem_type={problem.problem_type})を、決定論的アルゴリズム"
        f"「{algorithm.meta.name}」と LLM に直接解かせた場合とで比較した実測結果を、"
        "利用者向けに日本語で要約してください。\n\n"
        f"Algorithm 経路: status={algorithm_result.status}、"
        f"metrics={algorithm_result.metrics}、実行時間={algorithm_result.elapsed_ms:.1f}ms\n"
        f"LLM Only 経路({len(llm_results)}回試行): status一覧={llm_statuses}\n\n"
        f"制約遵守率: Algorithm={metrics.constraint_compliance_rate_algorithm:.0%} / "
        f"LLM={metrics.constraint_compliance_rate_llm:.0%}\n"
        f"最適性(1.0=Algorithmと同等): {metrics.optimality_avg_quality_ratio_llm}\n"
        f"再現性(LLMが出した構造の種類数): {metrics.reproducibility_distinct_solutions_llm}\n"
        f"実行時間中央値: Algorithm={metrics.execution_time_ms_algorithm:.1f}ms / "
        f"LLM={metrics.execution_time_ms_llm_median:.1f}ms\n"
        f"エラー率: LLM={metrics.error_rate_llm:.0%}"
    )


def _fallback_narrative(metrics: ComparisonMetrics) -> ComparisonNarrative:
    """LLM 呼び出し失敗時、metrics から直接組み立てる機械的な要約(Phase 13 `_fallback_response`
    と同じ設計)。"""
    return ComparisonNarrative(
        summary="LLM によるナレーション生成に失敗したため、数値集計のみ示します。",
        constraint_compliance_note=(
            f"Algorithm={metrics.constraint_compliance_rate_algorithm:.0%} / "
            f"LLM={metrics.constraint_compliance_rate_llm:.0%}"
        ),
        optimality_note=f"quality_ratio(平均)={metrics.optimality_avg_quality_ratio_llm}",
        reproducibility_note=f"distinct_solutions={metrics.reproducibility_distinct_solutions_llm}",
        verifiability_note=(
            "LLM の出力も Algorithm と同じ SolutionVerificationService で検証されています"
            "(ただし意思決定過程そのものは検証できません)。"
        ),
    )
