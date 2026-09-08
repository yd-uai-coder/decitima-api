"""作業単位 1-6: POST /api/v1/solve の契約。"""

import pytest
from httpx import ASGITransport, AsyncClient
from tests.fixtures.optimization import build_route_problem, build_shift_problem

from app.main import app


# 通常パターン
async def test_solve_route_returns_verified_solution(api) -> None:
    client, _user = api
    problem = build_route_problem(forbidden=["e_bd"], required=["C"])
    resp = await client.post("/api/v1/solve", json={"problem": problem.model_dump(mode="json")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["solution"]["status"] == "valid"
    assert body["solution"]["assignments"]["path_node_ids"] == ["A", "B", "C", "E"]
    assert body["solution"]["metrics"]["total_weight"] == 9.0
    assert body["problem_id"] and body["solution_id"]

# 永続化なし
async def test_solve_persist_false_has_null_ids(api) -> None:
    client, _user = api
    resp = await client.post(
        "/api/v1/solve",
        json={
            "problem": build_route_problem().model_dump(mode="json"),
            "persist": False,
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["problem_id"] is None and body["solution_id"] is None

# shift_schedulingの中にstrategyが登録されていないから400エラー
# route_planningの中にはDijkstraStrategyが登録されているから200:OK
async def test_solve_unsupported_problem_type_is_400(api) -> None:
    client, _user = api
    resp = await client.post(
        "/api/v1/solve",
        json={"problem": build_shift_problem().model_dump(mode="json")},
    )
    #shift_schedulingを用意したのでレスポンスステータスが200になる
    # assert resp.status_code == 400
    assert resp.status_code == 200
    print( resp.json())
    # shift_schedulingを用意したのでno algorithmは出ない
    # assert "no algorithm" in resp.json()["detail"].lower()


# shift_schedulingの中にstrategyが登録されていないから400エラー
# route_planningの中にはDijkstraStrategyが登録されているから200:OK
async def test_solve_no_algorithm_is_400(api, monkeypatch: pytest.MonkeyPatch) -> None:
    # Phase 6 で shift にも strategy が付いた。registry キーを空にして「候補ゼロ → 400」を確認
    from app.algorithms.registry import REGISTRY

    monkeypatch.setitem(REGISTRY, "shift_scheduling", [])
    client, _user = api
    resp = await client.post(
        "/api/v1/solve",
        json={"problem": build_shift_problem().model_dump(mode="json")},
    )
    assert resp.status_code == 400
    assert "no algorithm" in resp.json()["detail"].lower()


# 到達不能エラーの確認
async def test_solve_infeasible_problem_is_400(api) -> None:
    client, _user = api
    resp = await client.post(
        "/api/v1/solve",
        json={"problem": build_route_problem(forbidden=["e_ce", "e_de"]).model_dump(mode="json")},
    )
    # print( resp.json())
    assert resp.status_code == 400


async def test_solve_requires_authentication() -> None:
    # 認証ヘッダなしの素のクライアント
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as anon:
        resp = await anon.post(
            "/api/v1/solve",
            json={"problem": build_route_problem().model_dump(mode="json")},
        )
    assert resp.status_code == 401
