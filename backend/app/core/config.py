from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """環境変数・.envファイルから読み込むアプリケーション全体の設定値。"""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )

    # App
    PROJECT_NAME: str = "FastAPI LangChain Template"
    ENVIRONMENT: str = "development"
    DEBUG: bool = False
    API_V1_PREFIX: str = "/api/v1"

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000"]

    # Database
    DATABASE_URL: str

    # Redis
    REDIS_URL: str

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30
    REFRESH_TOKEN_EXPIRE_DAYS: int = 30

    # AI
    GOOGLE_API_KEY: str | None = None
    TAVILY_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    # Rate limit（チャットメッセージ送信のレート制限。単位時間あたりの上限回数）
    CHAT_RATE_LIMIT_PER_HOUR: int = 20
    CHAT_RATE_LIMIT_PER_DAY: int = 100


@lru_cache
def get_settings() -> Settings:
    """Settingsインスタンスを生成する。lru_cacheによりプロセス内では1回だけ生成される。"""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
