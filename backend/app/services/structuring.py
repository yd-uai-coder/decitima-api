"""LLM Problem Structuring のドメイン非依存な機構(純粋関数)+ サービス層。

`EXTRACTORS` は `app.algorithms.registry.REGISTRY` と同型の「problem_type → 実装候補」の
ディスパッチテーブル(1行足すだけで拡張できる)。`build_overrides` は LLM の抽出結果を
`apply_overrides` にそのまま渡せる overrides dict に組み立てる。
`ground_references` は LLM が生成した id 参照(constraints の items、data の単一 id 参照
フィールド)がベース問題のカタログに実在するかを確認する ── 既存 `ProblemValidationService` は
この一致を検査しないため(到達可能性等の計算に使うだけ)、README「LLM 出力は常に信頼しない」
の最後の砦として Phase 11 が追加する。

`ProblemStructuringService` は以前(テンプレート由来)の `ChatService` を置き換える
(レート制限 → 会話取得/作成 → ワークフロー呼び出し → 会話記録、という骨格は踏襲しつつ

`get_structuring_workflow` は関数内 import(`structure()` 冒頭)にしている ──
`app.ai.graph.nodes` がこのモジュールの `EXTRACTORS`/`catalog_entries`/`catalog_ids`/
`ground_references` を import するため、モジュール先頭で
`app.ai.graph.workflow -> app.ai.graph.nodes -> app.services.structuring` と辿ると循環
import になる。呼び出し時まで遅延させることで輪を断つ(実行時コストは無視できる ──
Python は2回目以降の import をキャッシュから返す)。
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import BaseModel
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.domain.problems.logistics import LogisticsData
from app.domain.problems.network_design import NetworkDesignData
from app.domain.problems.problem import (
    ForbiddenConstraint,
    OptimizationProblem,
    RequiredInclusionConstraint,
)
from app.domain.problems.project_manager import ProjectData
from app.domain.problems.route_planner import RouteData
from app.domain.problems.shift_scheduler import ShiftData
from app.domain.problems.travel_planner import TravelData
from app.models.conversation import Conversation
from app.repositories.conversation import ConversationRepository
from app.schemas.structuring import (
    ExtractedConstraint,
    ExtractedObjective,
    LogisticsDataPatch,
    ProjectDataPatch,
    RouteDataPatch,
    ShiftDataPatch,
    TravelDataPatch,
)
from app.services.errors import (
    ConversationNotFoundError,
    GenerationFailedError,
    InfeasibleProblemError,
    ProblemValidationError,
    RateLimitExceededError,
)
from app.services.rate_limit import RateLimit, RateLimiter

MAX_GENERATION_ATTEMPTS = 3  # LLM呼び出しの一時的な失敗に対する最大リトライ回数
RETRY_DELAY_SECONDS = 1.0  # リトライ間隔(秒)

logger = logging.getLogger(__name__)

# problem_type ごとの Data Patch スキーマ。新アルゴリズムの追加と同じく既存コードに触れず
# 1 行足すだけで拡張できる(app/algorithms/registry.py::REGISTRY と同型)。
# network_design はトップレベル・スカラーを持たないため None(= LLM を呼ばない)。
EXTRACTORS: dict[str, type[BaseModel] | None] = {
    "route_planning": RouteDataPatch,
    "network_design": None,
    "shift_scheduling": ShiftDataPatch,
    "travel_planning": TravelDataPatch,
    "project_scheduling": ProjectDataPatch,
    "logistics_planning": LogisticsDataPatch,
}


def build_overrides(
    objectives_patch: list[ExtractedObjective],
    constraints_patch: list[ExtractedConstraint],
    data_patch: dict[str, Any],
) -> dict[str, Any]:
    """LLM の抽出結果を `apply_overridesにそのまま渡せる overrides dict に組み立てる。

    objectives_patch が空なら「抽出できなかった」とみなしベースの objectives を維持する
    (overrides に "objectives" キーを含めない)。constraints は空リストも正当な意味
    (制約なし)を持つため、空でも常に "constraints" キーを含める。
    """
    overrides: dict[str, Any] = {
        "constraints": [c.model_dump(exclude_none=True) for c in constraints_patch]
    }
    if objectives_patch:
        overrides["objectives"] = [o.model_dump() for o in objectives_patch]
    if data_patch:
        overrides["data"] = data_patch
    return overrides


def catalog_ids(problem: OptimizationProblem) -> set[str]:
    """problem.data のカタログ(list フィールド)が持つ id を全て集める(ドメインごとに形が
    違うので isinstance で分岐。route はさらに edges も id 参照の対象になる)。"""
    data = problem.data
    if isinstance(data, RouteData):
        return {n.id for n in data.nodes} | {e.id for e in data.edges}
    if isinstance(data, NetworkDesignData):
        return {n.id for n in data.nodes} | {link.id for link in data.links}
    if isinstance(data, ShiftData):
        return {s.id for s in data.staff} | {slot.id for slot in data.slots}
    if isinstance(data, TravelData):
        return {p.id for p in data.places} | {leg.id for leg in data.legs}
    if isinstance(data, ProjectData):
        return {t.id for t in data.tasks} | {d.id for d in data.dependencies}
    if isinstance(data, LogisticsData):
        return (
            {n.id for n in data.nodes}
            | {seg.id for seg in data.segments}
            | {v.id for v in data.vehicles}
            | {d.id for d in data.deliveries}
        )
    return set()


def catalog_entries(problem: OptimizationProblem) -> list[tuple[str, str | None]]:
    """problem.data の「主要な名前付きエンティティ」を (id, name または label) のペアで返す。
    extract_objectives_constraintsのプロンプトに埋め込み、LLM に「id で参照する」
    ことを徹底させるために使う(catalog_ids と違い、edge/leg/segment のような無名の
    関係エンティティは含めない ── 人間が自然言語で名指しするのは大抵ノード側のため)。"""
    data = problem.data
    if isinstance(data, RouteData):
        return [(n.id, n.label) for n in data.nodes]
    if isinstance(data, NetworkDesignData):
        return [(n.id, n.label) for n in data.nodes]
    if isinstance(data, ShiftData):
        return [(s.id, s.name) for s in data.staff]
    if isinstance(data, TravelData):
        return [(p.id, p.name) for p in data.places]
    if isinstance(data, ProjectData):
        return [(t.id, t.name) for t in data.tasks]
    if isinstance(data, LogisticsData):
        return [(n.id, n.label) for n in data.nodes]
    return []


def ground_references(problem: OptimizationProblem, ids: set[str]) -> list[str]:
    """LLM が生成した id 参照がカタログに実在するかを確認する。対象は constraints の
    items(forbidden / required_inclusion)と、data の単一 id 参照フィールド
    (route の start/goal、travel の start、logistics の depot_id)。

    名前(name/label)は対象外 ── downstream の集計(`solution_element_ids` 等)は id で
    突き合わせるため、名前が紛れ込むのは「実在しない id」と同じ害(黙って無視される、または
    誤って missing 扱いになる)を持つ。プロンプト側で「必ず id を使う」ことを徹底し、ここは
    その契約が守られているかの最後の砦として機能する。
    """
    issues: list[str] = []
    for c in problem.constraints:
        if isinstance(c, (RequiredInclusionConstraint, ForbiddenConstraint)):
            issues.extend(
                f"{c.kind} constraint references unknown id {item!r}"
                for item in c.items
                if item not in ids
            )

    data = problem.data
    id_fields: list[tuple[str, str | None]] = []
    if isinstance(data, RouteData):
        id_fields = [("start", data.start), ("goal", data.goal)]
    elif isinstance(data, TravelData):
        id_fields = [("start", data.start)]
    elif isinstance(data, LogisticsData):
        id_fields = [("depot_id", data.depot_id)]
    issues.extend(
        f"data.{field_name} references unknown id {value!r}"
        for field_name, value in id_fields
        if value is not None and value not in ids
    )
    return issues


class ProblemStructuringService:
    """会話へのメッセージ送信、レート制限、Structuring ワークフロー呼び出しを取りまとめる
    サービス。以前(テンプレート由来)の `ChatService` を置き換える。"""

    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        # session: DB操作用の非同期セッション
        # redis: レート制限カウンタの保存に使うRedisクライアント
        self._session = session
        self._conversations = ConversationRepository(session)
        self._rate_limiter = RateLimiter(
            redis,
            resource="structure",
            limits=[
                RateLimit(window_seconds=3600, max_requests=settings.STRUCTURE_RATE_LIMIT_PER_HOUR),
                RateLimit(window_seconds=86400, max_requests=settings.STRUCTURE_RATE_LIMIT_PER_DAY),
            ],
        )

    async def structure(
        self,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID | None,
        text: str,
        bypass_rate_limit: bool = False,
    ) -> tuple[Conversation, OptimizationProblem]:
        """自然言語を構造化する。戻り値は (conversation, problem)。problem_type は
        `problem.problem_type`(Literal 型で確定済み)で取れるため別途返さない。"""
        if not bypass_rate_limit:
            await self._rate_limiter.enforce(str(user_id))

        conversation = await self._get_or_create_conversation(
            user_id=user_id, conversation_id=conversation_id, first_message=text
        )
        await self._conversations.add_message(
            conversation_id=conversation.id, role="user", content=text
        )

        from app.ai.graph.workflow import get_structuring_workflow  # 循環 import 回避(§冒頭)

        workflow = get_structuring_workflow()
        result = await self._invoke_with_retry(
            workflow.ainvoke,
            {
                "text": text,
                "problem_type": None,
                "base_problem": None,
                "objectives_patch": [],
                "constraints_patch": [],
                "data_patch": {},
                "notes": [],
                "problem": None,
            },
        )

        problem: OptimizationProblem = result["problem"]
        summary = _summarize(problem, result["notes"])
        await self._conversations.add_message(
            conversation_id=conversation.id, role="assistant", content=summary
        )
        await self._session.commit()
        return conversation, problem

    async def _get_or_create_conversation(
        self, *, user_id: uuid.UUID, conversation_id: uuid.UUID | None, first_message: str
    ) -> Conversation:
        """conversation_id未指定なら新規会話を作り、指定済みなら所有者チェックの上で取得する。"""
        if conversation_id is None:
            # 新規会話のタイトルは最初のメッセージ冒頭80文字を流用する
            title = first_message[:80]
            return await self._conversations.create(user_id=user_id, title=title)

        conversation = await self._conversations.get_by_id(conversation_id, user_id=user_id)
        if conversation is None:
            raise ConversationNotFoundError(f"Conversation {conversation_id} not found")
        return conversation

    async def _invoke_with_retry(
        self,
        invoke: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]],
        initial_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Structuring ワークフローを呼び出し、クォータ超過は即失敗、Validation/グラウンディング
        失敗(入力起因でリトライしても解消しない)はそのまま伝播、それ以外は規定回数まで
        リトライする。"""
        last_error: Exception | None = None
        # attempt: 1回目から最大MAX_GENERATION_ATTEMPTS回まで試行する
        for attempt in range(1, MAX_GENERATION_ATTEMPTS + 1):
            try:
                return await invoke(initial_state)
            except (ProblemValidationError, InfeasibleProblemError):
                raise
            except Exception as exc:
                if _is_quota_error(exc):
                    # クォータ超過はリトライしても解消しないため即座に諦める
                    raise RateLimitExceededError(
                        "AI provider quota exceeded, please try again later"
                    ) from exc
                last_error = exc
                # 元の例外を握りつぶすと原因不明の502だけが残るため、試行のたびに警告ログへ残す
                logger.warning(
                    "structuring workflow attempt %d/%d failed: %r",
                    attempt,
                    MAX_GENERATION_ATTEMPTS,
                    exc,
                )
                if attempt < MAX_GENERATION_ATTEMPTS:
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
        logger.error(
            "structuring workflow gave up after %d attempts", MAX_GENERATION_ATTEMPTS
        )
        raise GenerationFailedError(
            "Failed to structure the request after multiple attempts"
        ) from last_error


def _summarize(problem: OptimizationProblem, notes: list[str]) -> str:
    """構造化結果を人間が読める要約テキストにする(会話ログの assistant message 用)。
    LLM を再度呼ばずテンプレート文字列で組み立てる(コストを増やさないための非自明な判断)。"""
    parts = [f"{problem.problem_type} として構造化しました。"]
    if problem.objectives:
        parts.append("目的: " + ", ".join(o.target for o in problem.objectives))
    if problem.constraints:
        parts.append(f"制約 {len(problem.constraints)} 件")
    parts.extend(notes)
    return " / ".join(parts)


def _is_quota_error(exc: Exception) -> bool:
    """例外がGeminiのクォータ超過（429相当）を示すものかどうかを判定する。"""
    try:
        from google.genai.errors import APIError as GoogleAPIError
    except ImportError:
        # google-genaiが未インストールの環境向けフォールバック
        GoogleAPIError = None

    return (
        GoogleAPIError is not None
        and isinstance(exc, GoogleAPIError)
        and getattr(exc, "code", None) == 429
    )
