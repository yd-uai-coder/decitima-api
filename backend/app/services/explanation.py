# DeciTima samples │ 初出 Phase 13
"""Result Explanation サービス。

Result Explanationの実装。永続化済みの `Solution`(`produced_by` +
`metrics` + `violations` を必ず持つ `CandidateSolution`)を人間向けの説明文に変換する 

`AlgorithmRecommendationService`と同型: LangGraph を介さない素の async サービス、
DB は `OptimizationReadService` 経由の読み取りのみ(このサービス自体は永続化しない)、
LLM 呼び出しが失敗しても例外にせず `logger.warning` を残してグレースフルデグレードする。

`explain()` の結果を `solution_id` キーで Redis にキャッシュする(TTL付き)。
`Solution` は永続化後に不変なので同じ結果を再生成する意味が無く、Gemini API の実コストが
ある呼び出しの繰り返しを避ける
"""

from __future__ import annotations

import logging
import uuid
from typing import cast

from langchain_core.messages import HumanMessage
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm.gemini import get_gemini_llm
from app.core.config import settings
from app.domain.problems.algorithm_catalog import ALGORITHM_DESCRIPTIONS, describe_algorithm
from app.domain.problems.problem import OptimizationProblem
from app.domain.solutions.solution import CandidateSolution
from app.schemas.explanation import ExplanationResponse, LlmExplanation
from app.services.optimization_read import OptimizationReadService
from app.services.rate_limit import RateLimit, RateLimiter

logger = logging.getLogger(__name__)

_EXPLANATION_CACHE_TTL_SECONDS = 86400
def _explanation_cache_key(solution_id: uuid.UUID) -> str:
    return f"explain:{solution_id}"

def _alternatives_text(problem_type: str, used_name: str) -> str:
    """採用アルゴリズム以外の、同じ problem_type の候補の説明を並べる(比較材料)。"""
    others = {
        name: desc
        for (pt, name), desc in ALGORITHM_DESCRIPTIONS.items()
        if pt == problem_type and name != used_name
    }
    if not others:
        return "他に登録された候補アルゴリズムはありません。"
    return "\n".join(f"- {name}: {desc}" for name, desc in others.items())


def _explain_prompt(
    problem: OptimizationProblem, candidate: CandidateSolution, alternatives_text: str
) -> str:
    """LLM 説明生成用プロンプトを組み立てる。数値(metrics/violations)は検証済みの事実として
    そのまま渡し、LLM には「並べ替え・計算」でなく「narrate(説明)」だけをさせる
    (README「LLM に最適解を計算させない」の徹底 ── Phase 13 でも変わらない)。"""
    violations_text = (
        "\n".join(
            f"- [{v.severity}] {v.constraint_kind}: {v.message}" for v in candidate.violations
        )
        or "違反なし"
    )
    metrics_text = ", ".join(f"{k}={v}" for k, v in candidate.metrics.items()) or "(metrics なし)"
    return (
        f"次の最適化問題(problem_type={problem.problem_type})に対して"
        f"「{candidate.produced_by.name}」アルゴリズムが返した解を、利用者向けに日本語で説明してください。\n\n"
        f"採用アルゴリズム: {candidate.produced_by.name}"
        f"({describe_algorithm(problem.problem_type, candidate.produced_by.name)})\n"
        f"解のステータス: {candidate.status}\n"
        f"metrics: {metrics_text}\n"
        f"制約違反:\n{violations_text}\n"
        f"目的: {[o.target for o in problem.objectives]}\n\n"
        f"他の候補アルゴリズム:\n{alternatives_text}"
    )


def _fallback_response(
    solution_id: uuid.UUID, problem: OptimizationProblem, candidate: CandidateSolution
) -> ExplanationResponse:
    """LLM 呼び出し失敗時、metrics/violations から直接組み立てる機械的な要約。
    ナラティブは無いが、solve/verify が検証済みの事実(metrics・violations)はそのまま伝える
    (`AlgorithmRecommendationService` の「ルールのみで返す」フォールバックに対応)。"""
    metrics_text = ", ".join(f"{k}={v}" for k, v in candidate.metrics.items()) or "(metrics なし)"
    violations_text = (
        "; ".join(f"[{v.severity}] {v.message}" for v in candidate.violations) or "違反なし"
    )
    return ExplanationResponse(
        solution_id=solution_id,
        problem_type=problem.problem_type,
        algorithm_name=candidate.produced_by.name,
        why_this_solution=f"metrics: {metrics_text}",
        key_constraints=violations_text,
        algorithm_rationale=describe_algorithm(problem.problem_type, candidate.produced_by.name),
        alternatives_comparison="LLM 呼び出しに失敗したため比較文は生成されていません",
        improvement_notes="LLM 呼び出しに失敗したため改善提案は生成されていません",
        notes=["LLM 説明生成に失敗したため、機械的な要約のみ返しています"],
    )


class SolutionExplanationService:
    """POST /api/v1/solutions/{solution_id}/explain のユースケース。永続化しない
    (`AlgorithmRecommendationService` と同型 ── DB は読み取りにしか使わない)。"""

    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        # session: 永続化済みの Problem/Solution を読み取るためだけに使う(書き込みなし)
        # redis: レート制限カウンタの保存に使う非同期Redisクライアント
        self._read = OptimizationReadService(session)
        self._redis = redis
        self._rate_limiter = RateLimiter(
            redis,
            resource="explain",
            limits=[
                RateLimit(window_seconds=3600, max_requests=settings.EXPLAIN_RATE_LIMIT_PER_HOUR),
                RateLimit(window_seconds=86400, max_requests=settings.EXPLAIN_RATE_LIMIT_PER_DAY),
            ],
        )

    async def explain(
        self,
        solution_id: uuid.UUID,
        *,
        user_id: uuid.UUID,
        bypass_rate_limit: bool = False,
    ) -> ExplanationResponse:
        # bypass_rate_limit: superuser はレート制限を受けない(既存 solve/recommend と同じ方針)
        if not bypass_rate_limit:
            await self._rate_limiter.enforce(str(user_id))

        # get_solution/get_problem: 所有者スコープ付き読み取り(他ユーザーの解は 404)
        solution_row = await self._read.get_solution(solution_id, user_id=user_id)

        cache_key = _explanation_cache_key(solution_id)
        cached = await self._redis.get(cache_key)
        if cached is not None:
            return ExplanationResponse.model_validate_json(cached)

        problem_row = await self._read.get_problem(solution_row.problem_id, user_id=user_id)
        candidate = CandidateSolution.model_validate(solution_row.payload)
        problem = OptimizationProblem.model_validate(problem_row.payload)
        alternatives_text = _alternatives_text(problem.problem_type, candidate.produced_by.name)

        try:
            llm_result = await self._invoke_llm(problem, candidate, alternatives_text)
        except Exception as exc:  # noqa: BLE001 — 説明は補助機能。失敗しても機械的な要約は返す
            logger.warning("solution explanation LLM call failed: %r", exc)
            return _fallback_response(solution_id, problem, candidate)

        response = ExplanationResponse(
            solution_id=solution_id,
            problem_type=problem.problem_type,
            algorithm_name=candidate.produced_by.name,
            **llm_result.model_dump(),
        )
        await self._redis.set(
            cache_key, response.model_dump_json(), ex=_EXPLANATION_CACHE_TTL_SECONDS
        )
        return response

    async def _invoke_llm(
        self,
        problem: OptimizationProblem,
        candidate: CandidateSolution,
        alternatives_text: str,
    ) -> LlmExplanation:
        llm = get_gemini_llm(temperature=0).with_structured_output(LlmExplanation)
        prompt = _explain_prompt(problem, candidate, alternatives_text)
        result = await llm.ainvoke([HumanMessage(content=prompt)])
        return cast(LlmExplanation, result)
