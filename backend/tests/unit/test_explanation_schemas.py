"""作業単位 13-1: `app.schemas.explanation` のスキーマ検証。

テスト対象 / ドライバ / スタブ:
- 対象: `LlmExplanation` / `ExplanationResponse`(Pydantic モデル)
- ドライバ: このテスト関数
- スタブ不要 ── 対象が純粋なデータ検証で外部依存を呼ばないため。
"""

from __future__ import annotations

import uuid

import pytest
from pydantic import ValidationError

from app.schemas.explanation import ExplanationResponse, LlmExplanation


def test_llm_explanation_requires_all_five_fields() -> None:
    with pytest.raises(ValidationError):
        LlmExplanation.model_validate({"why_this_solution": "x"})


def test_explanation_response_notes_defaults_to_empty_list() -> None:
    response = ExplanationResponse(
        solution_id=uuid.uuid4(),
        problem_type="route_planning",
        algorithm_name="dijkstra",
        why_this_solution="x",
        key_constraints="x",
        algorithm_rationale="x",
        alternatives_comparison="x",
        improvement_notes="x",
    )
    assert response.notes == []
