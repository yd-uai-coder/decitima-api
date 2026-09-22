"""`run_isolated`(診断書 §3-5)── 重い計算をタイムアウトで本当に止められる実行方式。

テスト対象 / ドライバ / スタブ:
- 対象: `app.services.isolation.run_isolated`(thread / process の 2 方式)と、
  `SolveService.solve` が `SOLVE_ISOLATION=process` でも同じ結果を返すこと
- ドライバ: このテスト関数
- スタブ不要 ── 対象の価値は「本物の子プロセス(forkserver)を起動して kill できること」自体なので、
  マルチプロセスの部分は偽物に差し替えない。実行対象は `tests/fixtures/isolation_targets.py`
  の小さな純粋関数(子プロセスから import できるようモジュールレベルに置く)。
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import cast

import pytest
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from tests.fixtures import isolation_targets as T
from tests.fixtures.fake_redis import FakeRedis
from tests.fixtures.optimization import build_route_problem

from app.core.config import settings
from app.models.user import User
from app.schemas.optimization import SolveRequest
from app.services.errors import NoAlgorithmError, SolveTimeoutError
from app.services.isolation import IsolatedProcessError, run_isolated
from app.services.solve import SolveService


@pytest.fixture
def process_mode(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setattr(settings, "SOLVE_ISOLATION", "process")
    yield


def _is_gone(pid: int, wait: float = 3.0) -> bool:
    """pid のプロセスが消えた(またはゾンビ)なら True。kill 直後は回収待ちの数 ms がある。"""
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline:
        try:
            state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        except (FileNotFoundError, ProcessLookupError):
            return True
        if state in ("Z", "X"):  # ゾンビ = 既に死んでいて回収待ち
            return True
        time.sleep(0.05)
    return False


# --- thread(既定。従来と同じ挙動)------------------------------------------------------


async def test_thread_mode_returns_value_and_times_out() -> None:
    assert await run_isolated(T.add, 1, 2, timeout_seconds=5) == 3
    with pytest.raises(TimeoutError):
        await run_isolated(T.sleep_then_return, 1.0, timeout_seconds=0.1)


# --- process ---------------------------------------------------------------------------


@pytest.mark.usefixtures("process_mode")
async def test_process_mode_returns_value() -> None:
    assert await run_isolated(T.add, 20, 22, timeout_seconds=30) == 42


@pytest.mark.usefixtures("process_mode")
async def test_process_mode_reraises_the_child_exception_with_its_type() -> None:
    """子プロセスで起きた AppError は型ごと親へ運ばれ、そのまま再送出される
    (SolveService が期待する例外ハンドリングが変わらない)。"""
    with pytest.raises(NoAlgorithmError, match="no algorithm for x"):
        await run_isolated(T.raise_app_error, timeout_seconds=30)


@pytest.mark.usefixtures("process_mode")
async def test_process_mode_timeout_actually_kills_the_child(tmp_path: Path) -> None:
    """thread 方式との決定的な違い ── タイムアウト後に計算が走り続けない。"""
    pid_file = tmp_path / "pid"
    with pytest.raises(TimeoutError):
        await run_isolated(T.spin_and_record_pid, str(pid_file), timeout_seconds=1.0)

    assert _is_gone(int(pid_file.read_text()))


@pytest.mark.usefixtures("process_mode")
async def test_process_mode_kills_helper_processes_of_the_child_too(tmp_path: Path) -> None:
    """PuLP は外部の cbc プロセスを起動する ── 子だけ殺すと cbc が孤児になって CPU を使い続ける。
    プロセスグループごと kill するので、子が起動した外部プロセスも消える。"""
    pid_file = tmp_path / "helper_pid"
    with pytest.raises(TimeoutError):
        await run_isolated(T.spawn_helper_and_wait, str(pid_file), timeout_seconds=1.5)

    assert _is_gone(int(pid_file.read_text()))


@pytest.mark.usefixtures("process_mode")
async def test_process_mode_cancellation_kills_the_child(tmp_path: Path) -> None:
    """呼び出し側のキャンセル(クライアント切断)でも子プロセスを止める。"""
    pid_file = tmp_path / "pid"
    task = asyncio.create_task(
        run_isolated(T.spin_and_record_pid, str(pid_file), timeout_seconds=60)
    )
    for _ in range(100):  # 子が pid を書くまで待つ
        if pid_file.exists() and pid_file.read_text():
            break
        await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert _is_gone(int(pid_file.read_text()))


@pytest.mark.usefixtures("process_mode")
async def test_process_mode_reports_a_child_that_died_without_a_result() -> None:
    with pytest.raises(IsolatedProcessError, match="without a result"):
        await run_isolated(T.die_without_result, timeout_seconds=30)


@pytest.mark.usefixtures("process_mode")
async def test_process_mode_reports_an_unpicklable_result() -> None:
    with pytest.raises(IsolatedProcessError, match="could not be sent"):
        await run_isolated(T.return_unpicklable, timeout_seconds=30)


async def test_process_mode_limits_concurrent_children(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SOLVE_MAX_PROCESSES=1 なら、同時に 2 件来ても直列に処理される(fork の暴走を防ぐ)。"""
    monkeypatch.setattr(settings, "SOLVE_ISOLATION", "process")
    monkeypatch.setattr(settings, "SOLVE_MAX_PROCESSES", 1)
    await run_isolated(T.add, 1, 1, timeout_seconds=30)  # forkserver を先に温める

    start = time.monotonic()
    await asyncio.gather(
        run_isolated(T.sleep_then_return, 0.5, timeout_seconds=30),
        run_isolated(T.sleep_then_return, 0.5, timeout_seconds=30),
    )
    assert time.monotonic() - start >= 1.0


# --- SolveService を通した end-to-end -----------------------------------------------------


async def test_solve_service_gives_the_same_solution_in_thread_and_process_mode(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """process 方式でも SolveService の結果は thread 方式と一致する(pickle 往復で変わらない)。"""
    user = User(email="isolation@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()
    request = SolveRequest(problem=build_route_problem(), persist=False)

    async def _solve() -> dict[str, object]:
        outcome = await SolveService(db_session, cast(Redis, FakeRedis())).solve(
            user_id=user.id, request=request
        )
        return outcome.solution.model_dump(mode="json")

    monkeypatch.setattr(settings, "SOLVE_ISOLATION", "thread")
    in_thread = await _solve()
    monkeypatch.setattr(settings, "SOLVE_ISOLATION", "process")
    in_process = await _solve()

    assert in_process == in_thread
    assert in_process["status"] == "valid"


async def test_solve_service_timeout_in_process_mode_maps_to_solve_timeout_error(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """タイムアウトは process 方式でも SolveTimeoutError(504)になる。"""
    monkeypatch.setattr(settings, "SOLVE_ISOLATION", "process")
    monkeypatch.setattr(settings, "SOLVE_TIMEOUT_SECONDS", 0.001)  # 子の起動だけで超える
    user = User(email="isolation2@example.com", hashed_password="x")
    db_session.add(user)
    await db_session.flush()

    with pytest.raises(SolveTimeoutError):
        await SolveService(db_session, cast(Redis, FakeRedis())).solve(
            user_id=user.id,
            request=SolveRequest(problem=build_route_problem(), persist=False),
        )
    assert os.getpid()  # 何も残らず、テストプロセス自身は健在
