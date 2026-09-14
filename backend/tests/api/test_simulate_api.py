# DeciTima samples │ Phase 10
"""作業単位 10-4: POST /api/v1/simulate の契約。

結果のポーリングは既存の GET /api/v1/jobs/{id}(Phase 9-8)を再利用する設計(進行のルール
#17)なので、ここでは「投入 → 既存 jobs ルートで queued が見える」までを確認する
(succeeded まで進めるには実ワーカーが要るため、それは integration の領分 ── #12.4 参照)。
"""

from __future__ import annotations

import pytest
from tests.fixtures.optimization import build_project_problem


async def _patch_create_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _fake_create_pool(*_args: object, **_kwargs: object) -> object:
        class _Pool:
            async def enqueue_job(self, *_a: object, **_kw: object) -> None:
                pass

            async def aclose(self) -> None:
                pass

        return _Pool()

    monkeypatch.setattr("app.services.job.create_pool", _fake_create_pool)


async def test_simulate_route_returns_202_and_job_is_pollable_via_jobs_route(
    api, monkeypatch: pytest.MonkeyPatch
) -> None:
    await _patch_create_pool(monkeypatch)
    client, _user = api

    problem = build_project_problem()
    resp = await client.post(
        "/api/v1/simulate",
        json={
            "problem": problem.model_dump(mode="json"),
            "scenarios": [{"label": "tighter", "overrides": {"data": {"resource_capacity": 1}}}],
        },
    )
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    assert resp.json()["status"] == "queued"

    # GET /jobs/{id}(Phase 9-8)をそのまま再利用してポーリングできることを確認する
    poll = await client.get(f"/api/v1/jobs/{job_id}")
    assert poll.status_code == 200
    assert poll.json()["status"] == "queued"
    assert poll.json()["problem_type"] == "project_scheduling"


async def test_simulate_route_rejects_infeasible_base_problem(
    api, monkeypatch: pytest.MonkeyPatch
) -> None:
    from tests.fixtures.optimization import build_route_problem

    await _patch_create_pool(monkeypatch)
    client, _user = api

    problem = build_route_problem(forbidden=["e_ce", "e_de"])
    resp = await client.post(
        "/api/v1/simulate",
        json={
            "problem": problem.model_dump(mode="json"),
            "scenarios": [{"label": "noop", "overrides": {}}],
        },
    )
    assert resp.status_code == 400
