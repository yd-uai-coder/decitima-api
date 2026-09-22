"""診断書 §5 / §6 の是正のテスト(認証の強化・レート制限の原子化・タイムアウト上限)。

テスト対象 / ドライバ / スタブ:
- 対象: `AuthService.authenticate` / `refresh_access_token`、`AuthRateLimiter`、`RateLimiter`、
  `effective_timeout`、ユーザー入力スキーマの長さ制約
- ドライバ: このテスト関数 / `db_session` フィクスチャ
- スタブ: `tests.fixtures.fake_redis.FakeRedis`(incr / expire / pipeline だけ)+ 認証テスト用の
  最小 Redis(set / exists / delete)。時間・DB 以外の外部依存は無いので、それ以上は不要。
"""

from __future__ import annotations

from typing import Any, cast

import pytest
from pydantic import ValidationError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession
from tests.fixtures.fake_redis import FakeRedis

from app.core.config import settings
from app.schemas.user import UserCreate
from app.services.auth import AuthService
from app.services.auth_rate_limit import AuthRateLimiter
from app.services.errors import (
    InvalidCredentialsError,
    InvalidTokenError,
    RateLimitExceededError,
)
from app.services.rate_limit import RateLimit, RateLimiter
from app.services.timeouts import effective_timeout
from app.services.user import UserService


class _TokenRedis:
    """AuthService のリフレッシュトークン管理(set / exists / delete)だけを模した最小実装。"""

    def __init__(self) -> None:
        self.store: dict[str, str] = {}

    async def set(self, key: str, value: str, ex: int | None = None) -> None:  # noqa: ARG002
        self.store[key] = value

    async def exists(self, key: str) -> int:
        return int(key in self.store)

    async def delete(self, key: str) -> int:
        return int(self.store.pop(key, None) is not None)


def _auth(session: AsyncSession) -> AuthService:
    return AuthService(session, cast(Redis, _TokenRedis()))


async def _user(session: AsyncSession, *, active: bool = True):
    user = await UserService(session).create_user(email="frank@example.com", password="s3cret-pass")
    user.is_active = active
    await session.flush()
    return user


# --- 認証 -------------------------------------------------------------------------------


async def test_authenticate_verifies_against_dummy_hash_when_user_is_missing(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """ユーザー不在でも Argon2 検証を 1 回行う ── 応答時間の差でメールの存在を推測させない。"""
    calls: list[str] = []

    def _spy(plain: str, hashed: str) -> bool:
        calls.append(hashed)
        return False

    monkeypatch.setattr("app.services.auth.verify_password", _spy)

    with pytest.raises(InvalidCredentialsError):
        await _auth(db_session).authenticate(email="nobody@example.com", password="whatever")

    assert len(calls) == 1
    assert calls[0].startswith("$argon2")  # 実在ユーザーと同じ形式のハッシュに対して検証している


async def test_authenticate_uses_same_message_for_inactive_and_wrong_password(
    db_session: AsyncSession,
) -> None:
    """無効化済みユーザーに正しいパスワードを渡しても、不一致と同じ文言(区別させない)。"""
    await _user(db_session, active=False)

    with pytest.raises(InvalidCredentialsError) as inactive:
        await _auth(db_session).authenticate(email="frank@example.com", password="s3cret-pass")
    with pytest.raises(InvalidCredentialsError) as wrong:
        await _auth(db_session).authenticate(email="frank@example.com", password="nope")

    assert str(inactive.value) == str(wrong.value) == "Invalid email or password"


async def test_refresh_is_rejected_after_user_is_deactivated(db_session: AsyncSession) -> None:
    """有効なリフレッシュトークンを持っていても、無効化されたユーザーには再発行しない。"""
    user = await _user(db_session)
    auth = _auth(db_session)
    _, refresh_token = await auth.issue_tokens(user)

    user.is_active = False
    await db_session.flush()

    with pytest.raises(InvalidTokenError):
        await auth.refresh_access_token(refresh_token)


def test_user_create_enforces_password_length() -> None:
    with pytest.raises(ValidationError):
        UserCreate(email="a@example.com", password="short")
    with pytest.raises(ValidationError):
        UserCreate(email="a@example.com", password="x" * 129)  # Argon2 に巨大入力を渡させない
    assert UserCreate(email="a@example.com", password="long-enough-pw").password


# --- 認証のレート制限 -----------------------------------------------------------------------


async def test_login_is_limited_per_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_PER_IP_PER_HOUR", 2)
    limiter = AuthRateLimiter(cast(Redis, FakeRedis()))

    await limiter.enforce_login(ip="1.1.1.1", email="a@example.com")
    await limiter.enforce_login(ip="1.1.1.1", email="b@example.com")
    with pytest.raises(RateLimitExceededError):
        await limiter.enforce_login(ip="1.1.1.1", email="c@example.com")
    # 別 IP は別枠
    await limiter.enforce_login(ip="2.2.2.2", email="a@example.com")


async def test_login_is_limited_per_email_case_insensitively(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """IP を変えても、同じメール(大文字小文字違いを含む)への試行は数え続ける。"""
    monkeypatch.setattr(settings, "LOGIN_RATE_LIMIT_PER_EMAIL_PER_HOUR", 2)
    limiter = AuthRateLimiter(cast(Redis, FakeRedis()))

    await limiter.enforce_login(ip="1.1.1.1", email="Victim@Example.com")
    await limiter.enforce_login(ip="2.2.2.2", email="victim@example.com")
    with pytest.raises(RateLimitExceededError):
        await limiter.enforce_login(ip="3.3.3.3", email="  VICTIM@example.com ")


async def test_register_is_limited_per_ip(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "REGISTER_RATE_LIMIT_PER_IP_PER_HOUR", 1)
    limiter = AuthRateLimiter(cast(Redis, FakeRedis()))

    await limiter.enforce_register(ip="1.1.1.1")
    with pytest.raises(RateLimitExceededError):
        await limiter.enforce_register(ip="1.1.1.1")


# --- RateLimiter の原子化 -----------------------------------------------------------------


async def test_rate_limiter_uses_a_single_transaction_for_incr_and_expire() -> None:
    """incr と expire を別々に送ると、間でプロセスが落ちたとき TTL 無しキーが残る(永久ロック)。
    pipeline(MULTI/EXEC)で 1 往復にまとめ、expire は NX(TTL 未設定のときだけ)で送る。"""

    class _Spy(FakeRedis):
        def __init__(self) -> None:
            super().__init__()
            self.commands: list[tuple[str, dict[str, Any]]] = []

        async def incr(self, key: str) -> int:
            self.commands.append(("incr", {}))
            return await super().incr(key)

        async def expire(self, key: str, seconds: int, nx: bool = False) -> bool:
            self.commands.append(("expire", {"nx": nx}))
            return await super().expire(key, seconds, nx=nx)

    redis = _Spy()
    limiter = RateLimiter(
        cast(Redis, redis), resource="t", limits=[RateLimit(window_seconds=60, max_requests=5)]
    )
    await limiter.enforce("u1")

    assert redis.commands == [("incr", {}), ("expire", {"nx": True})]


async def test_rate_limiter_blocks_after_max_requests() -> None:
    limiter = RateLimiter(
        cast(Redis, FakeRedis()),
        resource="t",
        limits=[RateLimit(window_seconds=60, max_requests=2)],
    )
    await limiter.enforce("u1")
    await limiter.enforce("u1")
    with pytest.raises(RateLimitExceededError):
        await limiter.enforce("u1")


# --- タイムアウトの上限 -------------------------------------------------------------------


def test_effective_timeout_caps_user_value_at_server_limit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "SOLVE_TIMEOUT_SECONDS", 10.0)
    assert effective_timeout(None) == 10.0  # 未指定 -> 上限
    assert effective_timeout(0) == 10.0
    assert effective_timeout(3.0) == 3.0  # 短くするのは自由
    assert effective_timeout(100000.0) == 10.0  # 長くはできない


# --- 入力サイズ上限 -----------------------------------------------------------------------


def test_structuring_request_text_is_bounded() -> None:
    from app.schemas.structuring import StructuringRequest

    with pytest.raises(ValidationError):
        StructuringRequest(text="")
    with pytest.raises(ValidationError):
        StructuringRequest(text="あ" * 2001)
    assert StructuringRequest(text="あ" * 2000).text


def test_simulation_request_scenarios_are_bounded() -> None:
    from tests.fixtures.optimization import build_route_problem

    from app.schemas.simulation import ScenarioOverride, SimulationRequest

    scenario = ScenarioOverride(label="s", overrides={})
    problem = build_route_problem()
    with pytest.raises(ValidationError):
        SimulationRequest(problem=problem, scenarios=[scenario] * 21)
    assert SimulationRequest(problem=problem, scenarios=[scenario] * 20).scenarios
