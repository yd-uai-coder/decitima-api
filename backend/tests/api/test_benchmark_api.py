"""作業単位 3-3 / 3-4: POST /api/v1/benchmark と GET /api/v1/benchmarks/{id} の契約。

対象 = ルート + BenchmarkService + BenchmarkRunRepository + SolutionVerificationService。
ドライバ = httpx.AsyncClient(`api` フィクスチャ)。
スタブ = 依存差し替え(get_redis → FakeRedis、get_db → SQLite)。検証器・strategy は本物。
"""

import uuid

from httpx import ASGITransport, AsyncClient
from tests.fixtures.optimization import build_route_problem

from app.main import app


def _payload(**kw) -> dict:
    return {"problem": build_route_problem().model_dump(mode="json"), **kw}


async def test_benchmark_returns_entries(api) -> None:
    client, _user = api
    resp = await client.post("/api/v1/benchmark", json=_payload(runs=2))
    assert resp.status_code == 200
    body = resp.json()
    assert {e["algorithm"]["name"] for e in body["entries"]} == { "a_star","bellman_ford","brute_force", "dijkstra","dijkstra_nx"}
    first = body["entries"][0]
    assert "elapsed_ms_median" in first
    assert "operation_count" in first
    assert "quality_ratio" in first
    assert body["benchmark_id"] is not None


async def test_benchmark_respects_algorithms_and_runs(api) -> None:
    client, _user = api
    resp = await client.post(
        "/api/v1/benchmark", json=_payload(algorithms=["brute_force"], runs=1, persist=False)
    )
    assert resp.status_code == 200
    body = resp.json()
    assert [e["algorithm"]["name"] for e in body["entries"]] == ["brute_force"]
    assert body["benchmark_id"] is None


async def test_benchmark_invalid_problem_is_400(api) -> None:
    client, _user = api
    bad = build_route_problem(start="Z").model_dump(mode="json")
    resp = await client.post("/api/v1/benchmark", json={"problem": bad, "runs": 1})
    assert resp.status_code == 400


async def test_get_benchmark_run_roundtrip(api) -> None:
    client, _user = api
    created = await client.post("/api/v1/benchmark", json=_payload(runs=1))
    bid = created.json()["benchmark_id"]

    resp = await client.get(f"/api/v1/benchmarks/{bid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["problem_type"] == "route_planning"
    assert body["payload"]["runs"] == 1


async def test_get_missing_benchmark_run_is_404(api) -> None:
    client, _user = api
    resp = await client.get(f"/api/v1/benchmarks/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_benchmark_requires_authentication() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as anon:
        resp = await anon.post("/api/v1/benchmark", json=_payload(runs=1))
    assert resp.status_code == 401
