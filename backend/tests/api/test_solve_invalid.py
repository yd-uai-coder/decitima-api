"""作業単位 2-6: Invalid Solution Handling ── solve は invalid な解を「エラーではなく」返す。"""

from tests.fixtures.optimization import build_route_problem

# solutionがinvalidはエラーではない事の確認(solve)
async def test_solve_returns_invalid_solution_with_200(api) -> None:
    client, _user = api
    # Dijkstra は total_weight<=8 を無視して最短路(w9)を出す → Verification が invalid にする
    problem = build_route_problem(forbidden=["e_bd"], max_total_weight=8)
    resp = await client.post("/api/v1/solve", json={"problem": problem.model_dump(mode="json")})
    assert resp.status_code == 200  # 制約違反はエラーではない(Phase-0-6.md §4)
    body = resp.json()
    assert body["solution"]["status"] == "invalid"
    assert any(v["constraint_kind"] == "numeric_bound" for v in body["solution"]["violations"])
    # invalid でも永続化される(監査・再現性のため)
    assert body["problem_id"] and body["solution_id"]


# solutionがinvalidはエラーではない事の確認(solution)
async def test_persisted_invalid_solution_is_readable(api) -> None:
    client, _user = api
    problem = build_route_problem(forbidden=["e_bd"], max_total_weight=8)
    solve_resp = await client.post(
        "/api/v1/solve", json={"problem": problem.model_dump(mode="json")}
    )
    solution_id = solve_resp.json()["solution_id"]

    read = await client.get(f"/api/v1/solutions/{solution_id}")
    assert read.status_code == 200
    assert read.json()["status"] == "invalid"
