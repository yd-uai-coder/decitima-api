"""作業単位 2-5: POST /api/v1/verify の契約。"""

from httpx import ASGITransport, AsyncClient
from tests.fixtures.optimization import (
    build_route_problem,
    build_shift_problem,
    build_shift_solution,
)

from app.algorithms.graph.dijkstra import DijkstraStrategy
from app.main import app

_STRATEGY = DijkstraStrategy()


async def test_verify_valid_route_solution(api) -> None:
    client, _user = api
    problem = build_route_problem(forbidden=["e_bd"], required=["C"])
    solution = _STRATEGY.solve(problem)
    resp = await client.post(
        "/api/v1/verify",
        json={
            "problem": problem.model_dump(mode="json"),
            "solution": solution.model_dump(mode="json"),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "valid"
    assert body["violations"] == []


async def test_verify_flags_forbidden_edge_as_invalid(api) -> None:
    client, _user = api
    # 制約なしの最短(A-B-D-E, e_bd を使う)を、e_bd 禁止の問題に対して検証する
    bad = _STRATEGY.solve(build_route_problem())
    problem = build_route_problem(forbidden=["e_bd"])
    resp = await client.post(
        "/api/v1/verify",
        json={
            "problem": problem.model_dump(mode="json"),
            "solution": bad.model_dump(mode="json"),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "invalid"
    assert any(v["constraint_kind"] == "forbidden" for v in body["violations"])


async def test_verify_valid_shift_solution(api) -> None:
    client, _user = api
    problem = build_shift_problem()
    sol = build_shift_solution({"s1": ["tanaka"], "s2": ["sato"], "s3": ["ito"], "s4": ["sato"]})
    resp = await client.post(
        "/api/v1/verify",
        json={
            "problem": problem.model_dump(mode="json"),
            "solution": sol.model_dump(mode="json"),
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "valid"
    assert body["metrics"]["labor_cost"] == 21500.0


async def test_verify_invalid_shift_solution(api) -> None:
    client, _user = api
    problem = build_shift_problem()
    bad = build_shift_solution({"s1": ["tanaka"], "s2": [], "s3": ["ito"], "s4": ["sato"]})
    resp = await client.post(
        "/api/v1/verify",
        json={
            "problem": problem.model_dump(mode="json"),
            "solution": bad.model_dump(mode="json"),
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "invalid"


async def test_verify_requires_authentication() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as anon:
        resp = await anon.post(
            "/api/v1/verify",
            json={
                "problem": build_route_problem().model_dump(mode="json"),
                "solution": _STRATEGY.solve(build_route_problem()).model_dump(mode="json"),
            },
        )
    assert resp.status_code == 401
