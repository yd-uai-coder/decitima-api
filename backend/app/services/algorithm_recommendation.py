"""Algorithm Recommendation サービス。

README §9 の3段階セレクション(Step1 ルールベース / Step2 LLM推薦 / Step3 ベンチマークベース)
の Step2 にあたる。**最終決定は呼び出し側に委ねる**(LLM 単独では決めない) ── このサービスは
候補と理由を提示するだけで、既存の `/solve` の既定選択(`select_strategy`)には一切影響しない
(第二の消費者として無変更で再利用するだけ)。

`_ALGORITHM_DESCRIPTIONS` は `app.services.structuring._PROBLEM_TYPE_DESCRIPTIONS` と同型の
静的テーブル。`meta.name` は problem_type をまたいで重複する(例: "greedy" は shift/travel/
logistics の3つの別実装が持つ、"brute_force" は route/travel/logistics で3つ)ため、
キーは `(problem_type, name)` のタプルにする。

LLM 呼び出しが失敗しても例外にせず、ルールベースの結果のみで応答する(推薦は補助機能であり、
/solve のように失敗を呼び出し元に伝播させる必要が無いため)。ただし Phase 11-8 の教訓
(例外を握りつぶすとログに何も残らない)を踏まえ、失敗時は必ず `logger.warning` を残す。
"""

from __future__ import annotations

import logging
import uuid
from typing import cast

from langchain_core.messages import HumanMessage
from redis.asyncio import Redis

from app.ai.llm.gemini import get_gemini_llm
from app.algorithms.base import AlgorithmStrategy
from app.algorithms.registry import get_strategies
from app.core.config import settings
from app.domain.problems.algorithm_catalog import describe_algorithm
from app.domain.problems.problem import OptimizationProblem
from app.schemas.recommendation import (
    AlgorithmRecommendation,
    LlmRecommendation,
    RecommendationResponse,
)
from app.services.algorithm_selection import select_strategy
from app.services.errors import NoAlgorithmError
from app.services.rate_limit import RateLimit, RateLimiter

logger = logging.getLogger(__name__)

def _build_recommendation(
    strategy: AlgorithmStrategy,
    *,
    problem_type: str,
    rule_preferred: str,
    llm_rank: int | None = None,
    llm_comment: str | None = None,
) -> AlgorithmRecommendation:
    """1 strategy から AlgorithmRecommendation を組み立てる(3箇所の呼び出しで共有する
    ヘルパ ── 候補1件のみ/LLM失敗/通常系のどの経路でも同じ組み立てロジックを使う)。"""
    return AlgorithmRecommendation(
        name=strategy.meta.name,
        family=strategy.meta.family,
        implementation=strategy.meta.implementation,
        time_complexity=strategy.meta.time_complexity,
        description=describe_algorithm(problem_type, strategy.meta.name),
        is_rule_preferred=strategy.meta.name == rule_preferred,
        llm_rank=llm_rank,
        llm_comment=llm_comment,
    )


def _recommend_prompt(
    problem: OptimizationProblem,
    candidates: list[AlgorithmStrategy],
    rule_preferred: str,
) -> str:
    """LLM 推薦用プロンプトを組み立てる。候補は id ではなく meta.name で参照させる
    (grounding は `recommend()` 側で ranked_names/comments の name を照合して行う ──
    `app.services.structuring._data_prompt` と同じ「使ってよい id/名前の一覧を渡す」形)。"""
    lines = "\n".join(
        f"- {s.meta.name}: {describe_algorithm(problem.problem_type, s.meta.name)}"
        f"(計算量: {s.meta.time_complexity or '不明'})"
        for s in candidates
    )
    return (
        f"次の最適化問題(problem_type={problem.problem_type})に対して、"
        "下記の候補アルゴリズムをおすすめ順に並べ、それぞれに一言コメントを付けてください。\n"
        f"ルールベースの既定選択は「{rule_preferred}」です(参考情報。従う必要はありません)。\n\n"
        f"候補:\n{lines}\n\n"
        f"目的: {[o.target for o in problem.objectives]} / 制約数: {len(problem.constraints)}"
    )


class AlgorithmRecommendationService:
    """POST /api/v1/algorithms/recommend のユースケース。永続化しない(DB を触らない、
    `VerifyService` と同型)。"""

    def __init__(self, redis: Redis) -> None:
        # redis: レート制限カウンタの保存に使う非同期Redisクライアント
        self._rate_limiter = RateLimiter(
            redis,
            resource="recommend",
            limits=[
                RateLimit(
                    window_seconds=3600,
                    max_requests=settings.RECOMMEND_RATE_LIMIT_PER_HOUR,
                ),
                RateLimit(
                    window_seconds=86400,
                    max_requests=settings.RECOMMEND_RATE_LIMIT_PER_DAY,
                ),
            ],
        )

    async def recommend(
        self,
        *,
        user_id: uuid.UUID,
        problem: OptimizationProblem,
        bypass_rate_limit: bool = False,
    ) -> RecommendationResponse:
        # bypass_rate_limit: superuser はレート制限を受けない(既存 solve/verify と同じ方針)
        if not bypass_rate_limit:
            await self._rate_limiter.enforce(str(user_id))

        candidates = get_strategies(problem.problem_type)
        if not candidates:
            raise NoAlgorithmError(f"no algorithm registered for {problem.problem_type!r}")

        # rule_preferred: 既存 select_strategy をそのまま呼ぶ(第二の消費者、無変更)
        rule_preferred = select_strategy(problem).meta.name

        if len(candidates) == 1:
            # 候補が1件だけなら選びようが無いのでLLMを呼ばない(トークン節約)
            return RecommendationResponse(
                problem_type=problem.problem_type,
                rule_preferred=rule_preferred,
                recommendations=[
                    _build_recommendation(
                        candidates[0],
                        problem_type=problem.problem_type,
                        rule_preferred=rule_preferred,
                    )
                ],
                notes=["候補が1件のみのため LLM は呼び出していません"],
            )

        try:
            llm_result = await self._invoke_llm(problem, candidates, rule_preferred)
        except Exception as exc:  # noqa: BLE001 — 推薦は補助機能。失敗してもruleの結果は返す
            logger.warning("algorithm recommendation LLM call failed: %r", exc)
            return RecommendationResponse(
                problem_type=problem.problem_type,
                rule_preferred=rule_preferred,
                recommendations=[
                    _build_recommendation(
                        s,
                        problem_type=problem.problem_type,
                        rule_preferred=rule_preferred,
                    )
                    for s in candidates
                ],
                notes=["LLM 推薦の呼び出しに失敗したため、ルールベースの結果のみ返しています"],
            )

        valid_names = {s.meta.name for s in candidates}
        # rank_by_name / comment_by_name: 存在しない名前は黙って無視する(grounding)
        rank_by_name = {
            name: i + 1
            for i, name in enumerate(llm_result.ranked_names)
            if name in valid_names
        }
        comment_by_name = {
            c.name: c.comment for c in llm_result.comments if c.name in valid_names
        }

        recommendations = [
            _build_recommendation(
                s,
                problem_type=problem.problem_type,
                rule_preferred=rule_preferred,
                llm_rank=rank_by_name.get(s.meta.name),
                llm_comment=comment_by_name.get(s.meta.name),
            )
            for s in candidates
        ]
        # LLMがランク付けしたものを先頭に、無い場合はregistry順のまま末尾に残す
        recommendations.sort(key=lambda r: (r.llm_rank is None, r.llm_rank or 0))

        notes: list[str] = []
        dropped = (
            set(llm_result.ranked_names) | {c.name for c in llm_result.comments}
        ) - valid_names
        if dropped:
            notes.append(f"LLM が存在しない候補名を返したため無視しました: {sorted(dropped)}")

        return RecommendationResponse(
            problem_type=problem.problem_type,
            rule_preferred=rule_preferred,
            recommendations=recommendations,
            notes=notes,
        )

    async def _invoke_llm(
        self,
        problem: OptimizationProblem,
        candidates: list[AlgorithmStrategy],
        rule_preferred: str,
    ) -> LlmRecommendation:
        llm = get_gemini_llm(temperature=0).with_structured_output(LlmRecommendation)
        prompt = _recommend_prompt(problem, candidates, rule_preferred)
        # ainvoke: このサービスは(Structuringと違い)LangGraphを介さない素の async 関数なので、
        # 自分で非同期呼び出しする(Runnable は全て ainvoke を持つ ── プロバイダが真の async を
        # 実装していなくても内部で実行スレッドに逃がすため、イベントループを塞がない)
        result = await llm.ainvoke([HumanMessage(content=prompt)])
        return cast(LlmRecommendation, result)
