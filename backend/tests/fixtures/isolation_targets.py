"""`services/isolation.py` のテスト用の実行対象。

子プロセス(forkserver)から import されるので、テストファイルではなくここ(モジュールレベル)に
置く ── pytest のテストモジュール内の関数は子プロセス側で解決できないことがある。
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from app.services.errors import NoAlgorithmError


def add(a: int, b: int) -> int:
    return a + b


def raise_app_error() -> None:
    raise NoAlgorithmError("no algorithm for x")


def spin_and_record_pid(pid_file: str) -> None:
    """自分の pid を書いてから止まらずに回り続ける(タイムアウトで kill されるはず)。"""
    Path(pid_file).write_text(str(os.getpid()))
    while True:
        pass


def spawn_helper_and_wait(pid_file: str) -> None:
    """外部プロセス(PuLP の cbc 相当)を起動して待つ。その pid を書き出す。"""
    helper = subprocess.Popen(["sleep", "60"])
    Path(pid_file).write_text(str(helper.pid))
    helper.wait()


def die_without_result() -> None:
    os._exit(3)  # 結果を送らずに即死(OOM kill などの代役)


def return_unpicklable() -> object:
    return lambda: None  # pickle できない戻り値


def sleep_then_return(seconds: float) -> float:
    time.sleep(seconds)
    return seconds
