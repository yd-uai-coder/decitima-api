# DeciTima samples │ Phase 11
"""作業単位 11-7: `POST /api/v1/structure` の契約。

Structuring ワークフロー自体(LLM 呼び出し・ノード合成)は 11-3〜11-6 の unit テストで、
サービス層の振る舞い(会話記録・リトライ)は `test_structuring_service.py` で確認済みのため、
ここでは「API として正しく配線されているか」「返った problem がそのまま /solve に渡せるか」
だけに対象を絞る。
"""

from __future__ import annotations

from typing import Any

from app.domain.problems.base_problems import get_base_problem
from app.services.errors import ProblemValidationError


class _FakeWorkflow:
    """`get_structuring_workflow()` の代替。`ainvoke` が固定結果を返すか例外を送出する。"""

    def __init__(self, result: dict | Exception) -> None:
        self._result = result

    async def ainvoke(self, _state: dict) -> dict:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def _patch_workflow(monkeypatch: Any, result: dict | Exception) -> None:
    monkeypatch.setattr(
        "app.ai.graph.workflow.get_structuring_workflow", lambda: _FakeWorkflow(result)
    )


def _success_result(problem_type: str = "travel_planning") -> dict:
    return {"problem": get_base_problem(problem_type), "problem_type": problem_type, "notes": []}


async def test_structure_route_returns_a_problem_that_solve_can_consume(api, monkeypatch) -> None:
    client, _user = api
    _patch_workflow(monkeypatch, _success_result("travel_planning"))

    resp = await client.post("/api/v1/structure", json={"text": "5万円以内で東京を2日間旅行したい"})

    assert resp.status_code == 200
    body = resp.json()
    assert body["problem_type"] == "travel_planning"
    assert body["problem"]["problem_type"] == "travel_planning"
    assert "conversation_id" in body

    # 返ってきた problem をそのまま /solve に渡せる(README「LLM Service はスキーマ経由でのみ
    # Algorithm Engine と接続する」の実演)
    solve_resp = await client.post("/api/v1/solve", json={"problem": body["problem"]})
    assert solve_resp.status_code == 200


async def test_structure_route_reuses_conversation_across_calls(api, monkeypatch) -> None:
    client, _user = api
    _patch_workflow(monkeypatch, _success_result("route_planning"))

    first = await client.post("/api/v1/structure", json={"text": "1回目"})
    conversation_id = first.json()["conversation_id"]

    second = await client.post(
        "/api/v1/structure", json={"text": "2回目", "conversation_id": conversation_id}
    )

    assert second.status_code == 200
    assert second.json()["conversation_id"] == conversation_id


async def test_structure_route_maps_validation_error_to_400(api, monkeypatch) -> None:
    client, _user = api
    _patch_workflow(monkeypatch, ProblemValidationError("bad reference"))

    resp = await client.post("/api/v1/structure", json={"text": "存在しない場所を必ず通りたい"})

    assert resp.status_code == 400


async def test_structure_route_rejects_unknown_conversation_id(api, monkeypatch) -> None:
    import uuid

    client, _user = api
    _patch_workflow(monkeypatch, _success_result())

    resp = await client.post(
        "/api/v1/structure", json={"text": "dummy", "conversation_id": str(uuid.uuid4())}
    )

    assert resp.status_code == 404
