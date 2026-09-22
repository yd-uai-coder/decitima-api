"""重い純粋計算(`strategy.solve` など)を、タイムアウトで**本当に止められる**形で実行する。

これまでは `asyncio.wait_for(asyncio.to_thread(fn, ...))` で実行していた。スレッドは外から
止められないため、タイムアウト(504)を返した後も計算が走り続け、GIL と CPU を占有する
(実測: タイムアウト後の 2 秒間で CPU を 2.03 秒消費 ── 診断書 §3-5 / Phase 11-9 の「ゾンビ化」)。

`SOLVE_ISOLATION=process` のとき、呼び出しごとに使い捨ての子プロセスで実行し、タイムアウト・
キャンセルで **子プロセスを kill する**(実測 1.7ms で停止)。既定は従来どおり `thread`。

設計判断(いずれも実測に基づく。詳細は診断書 §3-5):
- `ProcessPoolExecutor` は使わない ── 実行中のタスクは `cancel()` できず、ワーカーを殺すと
  プール全体が `BrokenProcessPool` になる。「1 回限りの子プロセス + kill」が正しい道具。
- 起動方式は `forkserver`。`fork` はスレッドを持つサーバー(asyncio + `to_thread`)から呼ぶと
  ロック保持中のコピーによるデッドロックの恐れがあり(Python 3.12 以降は警告、3.14 で既定から
  外れる)、`spawn` は呼び出しごとに app 全体を import し直して約 1.2 秒かかる。forkserver は
  事前 import 済みの単一スレッドのプロセスから fork するため安全で、オーバーヘッドは約 50ms。
- 呼び出す関数は「純粋(DB・Redis に触れない)」なこと ── 境界を越えるのは引数と戻り値の pickle
  だけ。`strategy.solve` はこの契約(進行のルール・Phase 0 の純粋レイヤー)を満たしている。
- 子プロセスは自分のプロセスグループを作り、kill はグループごと行う。PuLP は外部の `cbc`
  プロセスを起動するため、Python 側だけ殺すと cbc が孤児になって CPU を使い続ける。
"""

from __future__ import annotations

import asyncio
import functools
import multiprocessing
import os
import signal
import weakref
from collections.abc import Callable
from multiprocessing.connection import Connection
from multiprocessing.context import ForkServerContext, ForkServerProcess
from typing import Any

from app.core.config import settings

# forkserver に事前 import させるモジュール。子プロセスはこれらが import 済みの状態で fork される
# (registry が全 strategy = networkx / ortools / pulp まで読み込むので、これで十分)
_FORKSERVER_PRELOAD = ["app.algorithms.registry", "app.services.algorithm_selection"]

# イベントループごとの同時実行数の上限(asyncio.Semaphore はループに紐づくため辞書で持つ)
_semaphores: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore] = (
    weakref.WeakKeyDictionary()
)


class IsolatedProcessError(RuntimeError):
    """子プロセスが結果を返さずに終了した(OOM kill・シグナル等)、または結果を送れなかった。"""


@functools.cache
def _context() -> ForkServerContext:
    """forkserver の multiprocessing コンテキスト(プロセス内で 1 度だけ作る)。"""
    ctx = multiprocessing.get_context("forkserver")
    ctx.set_forkserver_preload(_FORKSERVER_PRELOAD)
    return ctx  # type: ignore[return-value]


def _semaphore() -> asyncio.Semaphore:
    """現在のイベントループ用の、子プロセス同時実行数の上限(`SOLVE_MAX_PROCESSES`)。"""
    loop = asyncio.get_running_loop()
    sem = _semaphores.get(loop)
    if sem is None:
        sem = asyncio.Semaphore(settings.SOLVE_MAX_PROCESSES)
        _semaphores[loop] = sem
    return sem


def _child_main(conn: Connection, fn: Callable[..., Any], args: tuple[Any, ...]) -> None:
    """子プロセスの本体。fn(*args) の結果(または例外)を Pipe で親に返す。"""
    # 自分をプロセスグループの先頭にする ── 親が killpg で、この子が起動した外部プロセス
    # (PuLP の cbc 等)ごと止められるようにする
    os.setpgrp()
    try:
        outcome: tuple[str, Any] = ("ok", fn(*args))
    except BaseException as exc:  # noqa: BLE001 ── 例外も親へ運んで、親側で再送出する
        outcome = ("err", exc)
    try:
        conn.send(outcome)
    except Exception as exc:  # noqa: BLE001 ── pickle できない戻り値・例外
        conn.send(("err", IsolatedProcessError(f"outcome could not be sent: {exc!r}")))
    finally:
        conn.close()


def _kill(proc: ForkServerProcess) -> None:
    """子プロセスをグループごと即時終了させる。既に終了していれば何もしない。"""
    if proc.pid is None or proc.exitcode is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except (ProcessLookupError, PermissionError):
        # まだ setpgrp する前(グループが無い)など。子プロセス単体を殺す
        proc.kill()


async def _run_in_process[T](
    fn: Callable[..., T], args: tuple[Any, ...], timeout_seconds: float
) -> T:
    ctx = _context()
    parent_conn, child_conn = ctx.Pipe(duplex=False)
    proc = ctx.Process(target=_child_main, args=(child_conn, fn, args), daemon=True)
    try:
        # start() は引数の pickle と forkserver との通信でブロックするのでスレッドで行う
        await asyncio.to_thread(proc.start)
        child_conn.close()  # 親側では不要(閉じないと子の死亡を EOF で検知できない)
        # 結果が届く(または子が死んで EOF になる)まで timeout_seconds だけ待つ
        ready = await asyncio.to_thread(parent_conn.poll, timeout_seconds)
        if not ready:
            raise TimeoutError
        try:
            kind, value = await asyncio.to_thread(parent_conn.recv)
        except EOFError as exc:
            await asyncio.to_thread(proc.join, 1)
            raise IsolatedProcessError(
                f"isolated process exited without a result (exitcode={proc.exitcode})"
            ) from exc
        if kind == "err":
            raise value
        return value
    finally:
        # 正常終了・タイムアウト・呼び出し側のキャンセル(クライアント切断)のどれでも、
        # 残っている子プロセスを止めて回収する
        _kill(proc)
        parent_conn.close()
        child_conn.close()
        if proc.pid is not None:
            await asyncio.shield(asyncio.to_thread(proc.join, 5))


async def run_isolated[T](fn: Callable[..., T], *args: Any, timeout_seconds: float) -> T:
    """fn(*args) を実行して結果を返す。`timeout_seconds` を超えたら `TimeoutError`。

    settings.SOLVE_ISOLATION:
      - "thread"(既定): `asyncio.to_thread`。タイムアウトしてもスレッドは止まらない。
      - "process": 使い捨ての子プロセス。タイムアウトで kill され、CPU も解放される。
        fn と引数・戻り値は pickle できること(モジュールレベルの関数・純粋なデータ)。
    """
    if settings.SOLVE_ISOLATION != "process":
        return await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout_seconds)
    # 同時に走る子プロセス数を絞る(絞らないと同時リクエスト数だけ fork し、メモリ・CPU を使い切る)
    async with _semaphore():
        return await _run_in_process(fn, args, timeout_seconds)
