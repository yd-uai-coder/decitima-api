"""GET /api/v1/algorithms / /solutions/{id} / /problems/{id}/solutions。"""

import uuid

from tests.fixtures.optimization import build_route_problem


async def test_list_algorithms_returns_dijkstra(api) -> None:
    client, _user = api
    resp = await client.get("/api/v1/algorithms")
    assert resp.status_code == 200
    algos = resp.json()["algorithms"]
    dijkstra = next(a for a in algos if a["name"] == "dijkstra")
    assert dijkstra["family"] == "graph"
    assert dijkstra["implementation"] == "handwritten"
    assert "route_planning" in dijkstra["problem_types"]


async def test_solve_then_fetch_solution(api) -> None:
    client, _user = api
    solve = await client.post(
        "/api/v1/solve",
        json={"problem": build_route_problem().model_dump(mode="json")},
    )
    solution_id = solve.json()["solution_id"]
    problem_id = solve.json()["problem_id"]

    got = await client.get(f"/api/v1/solutions/{solution_id}")
    assert got.status_code == 200
    assert got.json()["status"] == "valid"

    listed = await client.get(f"/api/v1/problems/{problem_id}/solutions")
    assert listed.status_code == 200
    assert len(listed.json()) == 1


async def test_unknown_solution_is_404(api) -> None:
    client, _user = api
    resp = await client.get(f"/api/v1/solutions/{uuid.uuid4()}")
    assert resp.status_code == 404
