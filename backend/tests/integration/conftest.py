from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.database import Base, engine
from app.main import app


def ensure_test_database() -> None:
    """統合テストが誤って dev/本番データベースに対して Base.metadata.drop_all() を
    実行してしまう事故を防ぐ安全装置。DATABASE_URL に「test」を含まなければ即座に止める。

    背景：`docker compose run backend ...` は `.env` の DATABASE_URL（実データベース）を
    そのままコンテナに注入するため、`tests/conftest.py` の
    `os.environ.setdefault("DATABASE_URL", ...)` フォールバックは発動しない。この関数が
    無いと、統合テストのフィクスチャが実データベースの全テーブルを削除してしまう
    （2026-09-14 に実際に発生した事故）。
    """
    if "test" not in settings.DATABASE_URL:
        raise RuntimeError(
            f"DATABASE_URL がテスト用データベースを指していません({settings.DATABASE_URL!r})。"
            "統合テストは Base.metadata.drop_all() で全テーブルを消去するため、実データベースに"
            "対して実行すると危険です。docker compose run に "
            "-e DATABASE_URL=...(DB名に test を含むURL、例: app_test) を指定してください。"
        )


@pytest_asyncio.fixture
async def client() -> AsyncGenerator[AsyncClient]:
    """FastAPI -> PostgreSQL -> Redisの実スタックに疎通するテスト用HTTPクライアントを提供する。

    DATABASE_URL / REDIS_URLが実サービス（例：`docker compose up postgres redis`で
    起動したもの）を指している必要がある。
    """
    ensure_test_database()
    async with engine.begin() as conn:
        # テスト用DBに毎回まっさらな状態でテーブルを作り直す
        await conn.run_sync(Base.metadata.create_all)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as ac:
        yield ac

    async with engine.begin() as conn:
        # テスト終了後にテーブルを破棄し、次のテストに影響を残さないようにする
        await conn.run_sync(Base.metadata.drop_all)
