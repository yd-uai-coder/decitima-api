"""E2E テスト専用の固定 LLM フェイク(`settings.E2E_TESTING=true` のときだけ使われる)。

Playwright は本物のサーバープロセスに対して実行するため、pytest の `monkeypatch`(プロセス内
差し替え)は使えない ── `app/ai/llm/gemini.py::get_gemini_llm` がこのモジュールを参照する形で
経路そのものを切り替える。

対応するのは Structuring ワークフロー(Phase 11)が Travel Planner 向けに呼ぶ3スキーマだけ。
それ以外のスキーマは
`AlgorithmRecommendationCard`/`ExplanationCard`/`ComparisonCard` 用だが、これらは各カードの
ボタンを押したときだけ呼ばれ、E2E シナリオはそれらのボタンを押さないため
対応不要 ── 未対応スキーマは `NotImplementedError` で明示的に落とす(silent に誤った値を返さない)。
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from app.schemas.structuring import (
    ObjectivesConstraintsExtraction,
    ProblemTypeClassification,
    TravelDataPatch,
)

# schema クラス -> 固定の Structured Output。
# 「AIが理解した条件」は base_problem(Phase 11)をそのまま使う設計(全フィールド None)にし、
# E2E が検証したいのは抽出値の中身でなくパイプライン全体(分類→抽出→組み立て→検証→遷移→solve)
# が壊れずに繋がることなので、値そのものの妥当性リスクを最小化した。
_E2E_STRUCTURED_RESPONSES: dict[type[BaseModel], BaseModel] = {
    ProblemTypeClassification: ProblemTypeClassification(problem_type="travel_planning"),
    ObjectivesConstraintsExtraction: ObjectivesConstraintsExtraction(
        objectives=[], constraints=[]
    ),
    TravelDataPatch: TravelDataPatch(),
}


class _E2eStructuredLLM:
    """`with_structured_output(schema)` が返すサブクライアントのフェイク。

    # 写経の罠(実測で発覚): `app/ai/graph/nodes.py`(Structuring の分類/抽出ノード)は
    # `llm.invoke(...)`(**同期**)を呼ぶが、`app/services/explanation.py`/`comparison.py`は
    # `llm.ainvoke(...)`(**非同期**)を呼ぶ ── `tests/fixtures/fake_llm.py::_FakeStructuredLLM`
    # と同じく両方を実装しないと、片方だけの経路(E2Eで実際に踏むのは `invoke` 側)で
    # `AttributeError` → 500系エラーになる。最初の実装は `ainvoke` だけで、実際に
    # Playwright を走らせて初めて `POST /structure` が 502 で落ちることで発覚した。
    """

    def __init__(self, schema: type[BaseModel]) -> None:
        self._schema = schema

    def _resolve(self) -> BaseModel:
        try:
            return _E2E_STRUCTURED_RESPONSES[self._schema]
        except KeyError as exc:
            raise NotImplementedError(
                f"E2E フェイクLLMは {self._schema.__name__} に未対応です。"
                "対応スキーマ一覧に追加してください。"
            ) from exc

    def invoke(self, _messages: Any) -> BaseModel:
        return self._resolve()

    async def ainvoke(self, _messages: Any) -> BaseModel:
        return self._resolve()


class E2eFakeLLM:
    """`get_gemini_llm()` の戻り値のフェイク。構造化出力しか使わない前提。"""

    def with_structured_output(self, schema: type[BaseModel]) -> _E2eStructuredLLM:
        return _E2eStructuredLLM(schema)
