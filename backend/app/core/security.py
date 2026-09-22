import uuid
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from functools import lru_cache
from typing import Any

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import settings

_password_hash = PasswordHash((Argon2Hasher(),))


class TokenType(StrEnum):
    """JWTのペイロードに含める、トークン種別を表す列挙型。"""

    ACCESS = "access"
    REFRESH = "refresh"


def hash_password(password: str) -> str:
    """平文パスワードをArgon2でハッシュ化して返す。"""
    return _password_hash.hash(password)


@lru_cache
def dummy_password_hash() -> str:
    """存在しないユーザーに対する認証でも、実在ユーザーと同じ Argon2 検証コストを払うための
    ダミーハッシュ。ユーザー不在のとき検証を省くと応答時間が短くなり、その差でメールアドレスの
    存在を推測できる(ユーザー列挙)。初回呼び出し時に 1 度だけ生成する。"""
    return _password_hash.hash("dummy-password-for-timing-equalization")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """平文パスワードがハッシュ値と一致するかどうかを検証する。"""
    return _password_hash.verify(plain_password, hashed_password)


def _create_token(
    subject: str,
    token_type: TokenType,
    expires_delta: timedelta,
    extra_claims: dict[str, Any] | None = None,
) -> str:
    """subject・種別・有効期限をもとにJWTを1件生成する共通処理。"""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "type": token_type.value,
        "iat": now,
        "exp": now + expires_delta,
        # jti: トークンごとに一意なID。Redisでの失効管理に使う
        "jti": str(uuid.uuid4()),
    }
    if extra_claims:
        # extra_claimsが指定されていれば追加クレームとしてマージする
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def create_access_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    """アクセストークン（短命）を発行する。"""
    return _create_token(
        subject,
        TokenType.ACCESS,
        timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES),
        extra_claims,
    )


def create_refresh_token(subject: str, extra_claims: dict[str, Any] | None = None) -> str:
    """リフレッシュトークン（長命）を発行する。"""
    return _create_token(
        subject,
        TokenType.REFRESH,
        timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
        extra_claims,
    )


def decode_token(token: str) -> dict[str, Any]:
    """JWTを検証し、ペイロードを返す。検証に失敗した場合はjwt.PyJWTErrorを送出する。"""
    return jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
