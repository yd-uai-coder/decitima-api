import uuid

import jwt
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.security import (
    TokenType,
    create_access_token,
    create_refresh_token,
    decode_token,
    dummy_password_hash,
    verify_password,
)
from app.models.user import User
from app.repositories.user import UserRepository
from app.services.errors import InvalidCredentialsError, InvalidTokenError

_REFRESH_TOKEN_KEY_PREFIX = "refresh_token"


class AuthService:
    """ログイン認証、トークン発行、リフレッシュ、失効を担当するサービス。"""

    def __init__(self, session: AsyncSession, redis: Redis) -> None:
        # session: DB操作用の非同期セッション
        # redis: リフレッシュトークンの有効性管理に使うRedisクライアント
        self._session = session
        self._redis = redis
        self._users = UserRepository(session)

    async def authenticate(self, *, email: str, password: str) -> User:
        """メールアドレスとパスワードを検証し、一致すればUserを返す。"""
        user = await self._users.get_by_email(email)
        # ユーザー不在でもダミーハッシュに対して検証し、応答時間の差でメールの存在を推測させない
        hashed = user.hashed_password if user is not None else dummy_password_hash()
        password_ok = verify_password(password, hashed)
        # 「不在 / パスワード不一致 / 無効化済み」を同じ文言にして、どれかを区別させない
        if user is None or not password_ok or not user.is_active:
            raise InvalidCredentialsError("Invalid email or password")
        return user

    async def issue_tokens(self, user: User) -> tuple[str, str]:
        """アクセストークンとリフレッシュトークンを発行し、リフレッシュトークンをRedisに記録する。"""
        access_token = create_access_token(str(user.id))
        refresh_token = create_refresh_token(str(user.id))
        claims = decode_token(refresh_token)
        await self._store_refresh_token(
            user_id=user.id, jti=claims["jti"], expires_at=claims["exp"]
        )
        return access_token, refresh_token

    async def refresh_access_token(self, refresh_token: str) -> str:
        """リフレッシュトークンを検証し、有効であれば新しいアクセストークンを発行する。"""
        try:
            claims = decode_token(refresh_token)
        except jwt.PyJWTError as exc:
            raise InvalidTokenError("Invalid or expired refresh token") from exc

        if claims.get("type") != TokenType.REFRESH.value:
            raise InvalidTokenError("Token is not a refresh token")

        user_id = claims["sub"]
        jti = claims["jti"]
        if not await self._is_refresh_token_valid(user_id=user_id, jti=jti):
            raise InvalidTokenError("Refresh token has been revoked or expired")

        # 無効化・削除されたユーザーには、有効なリフレッシュトークンを持っていても再発行しない
        user = await self._users.get_by_id(uuid.UUID(user_id))
        if user is None or not user.is_active:
            raise InvalidTokenError("User is inactive or no longer exists")

        return create_access_token(user_id)

    async def revoke_refresh_token(self, refresh_token: str) -> None:
        """リフレッシュトークンをRedisから削除し、以後の再利用を無効化する（ログアウト用）。"""
        try:
            claims = decode_token(refresh_token)
        except jwt.PyJWTError:
            # 既に不正・期限切れのトークンは削除する必要が無いため何もしない
            return
        await self._redis.delete(self._redis_key(claims["sub"], claims["jti"]))

    async def _store_refresh_token(self, *, user_id: uuid.UUID, jti: str, expires_at: int) -> None:
        """発行したリフレッシュトークンのjtiをTTL付きでRedisに保存する。"""
        ttl_seconds = settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 60 * 60
        await self._redis.set(self._redis_key(str(user_id), jti), "1", ex=ttl_seconds)

    async def _is_refresh_token_valid(self, *, user_id: str, jti: str) -> bool:
        """指定したjtiのリフレッシュトークンがRedis上にまだ存在する（失効していない）かを確認する。"""
        return bool(await self._redis.exists(self._redis_key(user_id, jti)))

    @staticmethod
    def _redis_key(user_id: str, jti: str) -> str:
        """リフレッシュトークン管理用のRedisキーを組み立てる。"""
        return f"{_REFRESH_TOKEN_KEY_PREFIX}:{user_id}:{jti}"
