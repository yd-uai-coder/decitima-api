"""タイムアウト値の解決。solve / benchmark / simulate が共有する。"""

from __future__ import annotations

from app.core.config import settings


def effective_timeout(requested: float | None) -> float:
    """利用者が指定した `timeout_seconds` を、サーバー設定の上限で頭打ちにして返す。

    requested: リクエストの `timeout_seconds`(None なら未指定)。
    利用者は上限より「短く」はできるが「長く」はできない ── 上限が無いと、巨大な値を指定して
    (タイムアウトしても止まらない)計算スレッドを長時間占有させられる(診断書 §5-1)。
    """
    limit = settings.SOLVE_TIMEOUT_SECONDS
    if not requested:
        return limit
    return min(requested, limit)
