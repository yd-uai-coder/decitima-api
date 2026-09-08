"""分析トラック専用の DB 接続。

`app.core.database.engine` は共有しない ── 分析は API とは別プロセスで、単発の読み取り
しかしないため、その場でエンジンを作って dispose（破棄) する。
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine
    )

from app.core.config import settings


@asynccontextmanager # async with で使える非同期コンテキストマネージャを作る
async def session_scope() -> AsyncGenerator[AsyncSession]:
    """`settings.DATABASE_URL` への独立した async セッションを 1 つ供給する。"""
    engine = create_async_engine(
        settings.DATABASE_URL,
        echo=settings.DEBUG,
        pool_pre_ping=True
        )
    
    factory = async_sessionmaker(
        engine,
        expire_on_commit=False
      )

    try:
        async with factory() as session:
            yield session
    finally:
        await engine.dispose() #使い終わったら破棄
