"""API テスト用のフィクスチャ。

実 PG / Redis は不要(Phase-0-9.md §1.3)。get_db をインメモリ SQLite、get_redis を
FakeRedis に差し替え、テスト内でユーザーを1件作って JWT を発行する。
"""

from collections.abc import AsyncGenerator

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from tests.fixtures.fake_redis import FakeRedis

import app.models  # noqa: F401  Base.metadata に Problem/Solution を登録する
from app.core.database import Base, get_db
from app.core.security import create_access_token
from app.infrastructure.redis import get_redis
from app.main import app
from app.models.user import User


@pytest_asyncio.fixture
async def api(monkeypatch) -> AsyncGenerator[tuple[AsyncClient, User]]:
    """(認証ヘッダ付き AsyncClient, その所有ユーザー) を返す。"""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)

    async with session_factory() as session:
        user = User(email="solver@example.com", hashed_password="x")
        session.add(user)
        await session.commit()

        async def _get_db() -> AsyncGenerator[AsyncSession]:
            async with session_factory() as s:
                yield s

        fake_redis = FakeRedis()
        app.dependency_overrides[get_db] = _get_db
        app.dependency_overrides[get_redis] = lambda: fake_redis

        token = create_access_token(str(user.id))
        transport = ASGITransport(app=app)
        async with AsyncClient(
            transport=transport,
            base_url="http://testserver",
            headers={"Authorization": f"Bearer {token}"},
        ) as client:
            yield client, user

        app.dependency_overrides.clear()

    await engine.dispose()
