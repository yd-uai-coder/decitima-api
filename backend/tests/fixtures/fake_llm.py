"""LLM クライアントの挙動を模したテスト用スタブ。

`with_structured_output(schema)` の呼び出しごとに `schema` を `structured_output_calls` に
記録する ── どのドメインでどのスキーマが使われたかの検証で使う。
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import AIMessage
from pydantic import BaseModel


class FakeLLM:
    """Gemini LLM クライアント(`get_gemini_llm` の戻り値)の挙動を模したスタブ。"""

    def __init__(self, content: str | None = None, structured: BaseModel | None = None) -> None:
        # content: invoke()が返すAIMessageの本文
        # structured: with_structured_output().invoke()が返す構造化レスポンス
        self._content = content
        self._structured = structured
        self.structured_output_calls: list[type[BaseModel]] = []

    def invoke(self, _messages: Any) -> AIMessage:
        """通常のinvoke呼び出しの結果としてAIMessageを返す。"""
        return AIMessage(content=self._content)

    def with_structured_output(self, schema: type[BaseModel]) -> _FakeStructuredLLM:
        """構造化出力用のサブクライアントを返す。呼ばれた schema を記録する。"""
        self.structured_output_calls.append(schema)
        return _FakeStructuredLLM(self._structured)


class _FakeStructuredLLM:
    """with_structured_output()が返す、構造化レスポンスのみを返すテスト用スタブ。"""

    def __init__(self, structured: BaseModel | None) -> None:
        self._structured = structured

    def invoke(self, _messages: Any) -> BaseModel | None:
        """構造化済みレスポンスをそのまま返す。"""
        return self._structured
