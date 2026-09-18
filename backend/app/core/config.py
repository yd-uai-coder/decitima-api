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
    PROJECT_NAME: str = "DeciTima API"
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
    GEMINI_MODEL: str = "gemini-3.1-flash-lite"

    # Structuring API のレート制限（単位時間あたりの上限回数）
    STRUCTURE_RATE_LIMIT_PER_HOUR: int = 20
    STRUCTURE_RATE_LIMIT_PER_DAY: int = 100

    # Rate limit（チャットメッセージ送信のレート制限。単位時間あたりの上限回数）
    CHAT_RATE_LIMIT_PER_HOUR: int = 20
    CHAT_RATE_LIMIT_PER_DAY: int = 100

    # Rate limit（Decitimaのレート制限。単位時間あたりの上限回数）
    SOLVE_RATE_LIMIT_PER_HOUR: int = 20
    SOLVE_RATE_LIMIT_PER_DAY: int = 100
    SOLVE_TIMEOUT_SECONDS: float = 10.0

    # verifyの時間上限
    VERIFY_RATE_LIMIT_PER_HOUR: int = 60

    # BenchMark（Decitimaのレート制限。単位時間あたりの上限回数）
    BENCHMARK_RATE_LIMIT_PER_HOUR: int = 10
    BENCHMARK_RATE_LIMIT_PER_DAY: int = 50

    # Job（ジョブキュー投入のレート制限。単位時間あたりの上限回数。Phase 9-8）
    JOB_SUBMIT_RATE_LIMIT_PER_HOUR: int = 20
    JOB_SUBMIT_RATE_LIMIT_PER_DAY: int = 100

    # Simulate（シナリオ一括実行のレート制限。solve/job より重いので別枠。Phase 10-4）
    SIMULATE_SUBMIT_RATE_LIMIT_PER_HOUR: int = 10
    SIMULATE_SUBMIT_RATE_LIMIT_PER_DAY: int = 50

    # Algorithm Recommendation のレート制限（単位時間あたりの上限回数）
    RECOMMEND_RATE_LIMIT_PER_HOUR: int = 20
    RECOMMEND_RATE_LIMIT_PER_DAY: int = 100

    #  Result Explanation のレート制限（単位時間あたりの上限回数）
    EXPLAIN_RATE_LIMIT_PER_HOUR: int = 20
    EXPLAIN_RATE_LIMIT_PER_DAY: int = 100

    # LLM vs Algorithm Comparison のレート制限(単位時間あたりの上限回数)。
    # 1 リクエストで LLM を最大 llm_runs(既定5、上限20)回呼ぶため Benchmark と同程度に絞る
    COMPARE_RATE_LIMIT_PER_HOUR: int = 10
    COMPARE_RATE_LIMIT_PER_DAY: int = 50

    # arq ワーカーの同時実行ジョブ数(WorkerSettings.max_jobs)。
    # solve_job は CPU バウンドな solve() を GIL 下で実行するため、同時実行数を増やしても
    # 真の並列化はされない(実測は `Phase-15-5.md`)。arq 既定の 10 は I/O バウンドな
    # ワークロード向けの値で、この worker には過大 ── VPS の実コア数に応じて調整する前提で
    # env 変数化し、既定値は控えめな 4 にする。
    WORKER_MAX_JOBS: int = 4

    # app/core/config.py(改訂、抜粋)
    # (Phase 15-9) E2E テスト専用フラグ。true のとき get_gemini_llm() は実際の Gemini API を
    # 呼ばず、決定論的な固定応答を返すフェイクを返す。既定は false(本番は絶対に有効化しない。
    # .env にも書かず E2E 実行時だけ環境変数で渡す)。
    E2E_TESTING: bool = False

    
@lru_cache
def get_settings() -> Settings:
    """Settingsインスタンスを生成する。lru_cacheによりプロセス内では1回だけ生成される。"""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
