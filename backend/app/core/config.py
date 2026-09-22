from functools import lru_cache
from typing import Literal, Self

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 本番で許す JWT 秘密鍵の最小長(HS256 の鍵として 256 bit = 32 バイト以上が目安)
_JWT_SECRET_MIN_LENGTH = 32


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

    # 重い純粋計算(strategy.solve 等)の実行方式。
    #   "thread": 既定。タイムアウトしても計算スレッドは止まらない(GIL・CPU を占有し続ける)。
    #   "process": 使い捨ての子プロセス(forkserver)。タイムアウト・キャンセルで kill され、
    #              CPU が解放され、複数の solve が真に並列に走る。呼び出しごとに約 50ms かかる。
    # テストは偽の strategy を monkeypatch しており子プロセスには伝わらないため既定は thread。
    # 本番で有効にする手順と実測は `textbook/appendix/project-diagnosis.md` §3-5。
    SOLVE_ISOLATION: Literal["thread", "process"] = "thread"
    # "process" のときの同時に走らせる子プロセス数の上限(VPS の実コア数に合わせる)
    SOLVE_MAX_PROCESSES: int = 4

    # リクエストボディの上限(バイト)。問題定義は数百 KB あれば足りる(Phase 15-1 の性能テストの
    # 最大規模でも 1MB 未満)。nginx の client_max_body_size と同じ値に揃える。
    MAX_REQUEST_BODY_BYTES: int = 2_000_000

    # 認証エンドポイントのレート制限(総当たり・大量登録の対策。単位時間あたりの上限回数)。
    # IP 単位は NAT 配下の複数人が巻き込まれ得るため、メール単位より緩くする。
    LOGIN_RATE_LIMIT_PER_IP_PER_HOUR: int = 30
    LOGIN_RATE_LIMIT_PER_EMAIL_PER_HOUR: int = 20
    REGISTER_RATE_LIMIT_PER_IP_PER_HOUR: int = 10

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

    @model_validator(mode="after")
    def _reject_unsafe_production_settings(self) -> Self:
        """`ENVIRONMENT=production` で起動してはいけない設定を、起動時(設定の読み込み時)に弾く。
        設定ミスは「動くが危険」な状態になりやすい(E2E フェイクが本番で有効になっても
        利用者には正常な応答に見える)ため、実行時でなく起動時に落とす。"""
        if self.ENVIRONMENT != "production":
            return self
        problems: list[str] = []
        if self.E2E_TESTING:
            problems.append("E2E_TESTING=true(LLM が固定応答のフェイクになる)")
        if self.DEBUG:
            problems.append("DEBUG=true(SQL のログ出力などで機密が漏れる)")
        secret = self.JWT_SECRET_KEY
        if len(secret) < _JWT_SECRET_MIN_LENGTH or secret.lower().startswith("change-me"):
            problems.append(
                f"JWT_SECRET_KEY が短い(<{_JWT_SECRET_MIN_LENGTH} 文字)か、"
                ".env.example のプレースホルダのまま"
            )
        if problems:
            raise ValueError(
                "本番(ENVIRONMENT=production)で許されない設定: " + " / ".join(problems)
            )
        return self


@lru_cache
def get_settings() -> Settings:
    """Settingsインスタンスを生成する。lru_cacheによりプロセス内では1回だけ生成される。"""
    return Settings()  # type: ignore[call-arg]


settings = get_settings()
