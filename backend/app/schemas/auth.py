from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    """ログインAPIのリクエストボディ。"""

    email: EmailStr
    # 上限だけ課す(既存ユーザーの短いパスワードで入れなくならないよう下限は課さない)
    password: str = Field(max_length=128)


class TokenPair(BaseModel):
    """ログイン成功時に返すアクセストークンとリフレッシュトークンの組。"""

    access_token: str
    refresh_token: str
    token_type: str = "bearer"


class RefreshRequest(BaseModel):
    """トークン更新・ログアウトAPIのリクエストボディ。"""

    refresh_token: str


class AccessToken(BaseModel):
    """トークン更新APIのレスポンスボディ。"""

    access_token: str
    token_type: str = "bearer"
