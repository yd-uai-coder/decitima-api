"""`Settings` の本番向け安全検証(診断書 §6-1 / §6-6)。

テスト対象 / ドライバ / スタブ:
- 対象: `Settings` の `model_validator`(`ENVIRONMENT=production` で危険な設定を起動時に拒否)
- ドライバ: このテスト関数。`Settings(_env_file=None, ...)` を直接構築する
- スタブ不要 ── 対象は環境変数の検証だけの純粋なモデルで外部依存を呼ばない
"""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from app.core.config import Settings

_GOOD_SECRET = "s" * 48


def _settings(**overrides: Any) -> Settings:
    base: dict[str, Any] = {
        "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
        "REDIS_URL": "redis://localhost:6379",
        "JWT_SECRET_KEY": _GOOD_SECRET,
    }
    return Settings(_env_file=None, **{**base, **overrides})  # type: ignore[call-arg]


def test_production_rejects_e2e_testing_flag() -> None:
    with pytest.raises(ValidationError, match="E2E_TESTING"):
        _settings(ENVIRONMENT="production", E2E_TESTING=True)


def test_production_rejects_debug() -> None:
    with pytest.raises(ValidationError, match="DEBUG"):
        _settings(ENVIRONMENT="production", DEBUG=True)


@pytest.mark.parametrize(
    "secret", ["short", "change-me-to-a-random-64-char-secret-change-me-xxxxxxxx"]
)
def test_production_rejects_weak_or_placeholder_jwt_secret(secret: str) -> None:
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        _settings(ENVIRONMENT="production", JWT_SECRET_KEY=secret)


def test_production_accepts_safe_settings() -> None:
    assert _settings(ENVIRONMENT="production").ENVIRONMENT == "production"


def test_development_allows_e2e_and_short_secret() -> None:
    """開発・CI では従来どおり(E2E フェイクや短い秘密鍵を許す)。"""
    s = _settings(ENVIRONMENT="development", E2E_TESTING=True, JWT_SECRET_KEY="ci-only")
    assert s.E2E_TESTING is True
