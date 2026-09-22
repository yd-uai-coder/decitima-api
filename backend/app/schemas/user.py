import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# パスワード長の範囲。上限は Argon2 に巨大な入力を渡して CPU を浪費させる攻撃の対策。
PASSWORD_MIN_LENGTH = 10
PASSWORD_MAX_LENGTH = 128


class UserBase(BaseModel):
    """ユーザー関連スキーマ間で共通するフィールドをまとめた基底クラス。"""

    email: EmailStr
    full_name: str | None = None


class UserCreate(UserBase):
    """ユーザー登録APIのリクエストボディ。"""

    password: str = Field(min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH)


class UserUpdate(BaseModel):
    """ユーザー更新APIのリクエストボディ（指定したフィールドのみ更新する想定）。"""

    full_name: str | None = None
    password: str | None = Field(
        default=None, min_length=PASSWORD_MIN_LENGTH, max_length=PASSWORD_MAX_LENGTH
    )


class UserRead(UserBase):
    """ユーザー情報をAPIレスポンスとして返す際のスキーマ（パスワードは含まない）。"""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    is_active: bool
    is_superuser: bool
    created_at: datetime
