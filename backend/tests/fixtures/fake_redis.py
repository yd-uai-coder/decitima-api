"""レート制限テスト用の最小 FakeRedis。RateLimiter が使う incr / expire だけ実装する。

既存 tests/unit/test_auth_service.py の FakeRedis(set/exists/delete)と別物なので、
DeciTima 側のテストはこちらを使う。
"""

from __future__ import annotations


class FakeRedis:
    """redis.asyncio.Redis の incr / expire だけを模したインメモリ実装。"""

    def __init__(self) -> None:
        self._counts: dict[str, int] = {}
        self._values: dict[str, str] = {}

    async def incr(self, key: str) -> int:
        """key のカウンタを 1 増やして増加後の値を返す。"""
        self._counts[key] = self._counts.get(key, 0) + 1
        return self._counts[key]

    async def expire(self, key: str, seconds: int) -> bool:  # noqa: ARG002
        """TTL 設定。テストでは寿命を管理しないので何もしない。"""
        return True
    
    async def get(self, key: str) -> str | None:
        """key の値を返す(無ければ None)。"""
        return self._values.get(key)

    async def set(self, key: str, value: str, *, ex: int | None = None) -> bool:  # noqa: ARG002
        """key に値を設定する。`ex`(TTL秒)はテストでは失効させないので記録しない。"""
        self._values[key] = value
        return True
