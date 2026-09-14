# DeciTima samples │ Phase 3
"""作業単位 3-8: analysis.export。

対象 = `dump_rows`(session → JSONL の純粋部分)。ドライバ = `db_session`(インメモリ SQLite)+
`BenchmarkRun` を数行入れる。**スタブ不要** ── SQLite セッションが実 DB の代役。
`export_table`(`session_scope` で実 DB を開く CLI ラッパ)はここでは呼ばない。
"""

import json
import uuid
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from analysis.export import dump_rows
from app.models.optimization import BenchmarkRun
from app.models.user import User


async def _user(session: AsyncSession) -> User:
    u = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x")
    session.add(u)
    await session.flush()
    return u


async def test_dump_rows_writes_one_json_per_line(db_session: AsyncSession, tmp_path: Path) -> None:
    user = await _user(db_session)
    for i in range(3):
        db_session.add(
            BenchmarkRun(
                user_id=user.id,
                problem_type="route_planning",
                payload={"problem": {}, "runs": i, "entries": []},
            )
        )
    await db_session.commit()

    out = tmp_path / "b.jsonl"
    n = await dump_rows(db_session, "benchmark_runs", out)
    assert n == 3

    lines = out.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 3
    rec = json.loads(lines[0])
    assert rec["problem_type"] == "route_planning"
    assert isinstance(rec["id"], str)  # uuid は文字列化される
    assert isinstance(rec["payload"], dict)


async def test_dump_rows_filters_by_user(db_session: AsyncSession, tmp_path: Path) -> None:
    a, b = await _user(db_session), await _user(db_session)
    db_session.add(BenchmarkRun(user_id=a.id, problem_type="route_planning", payload={}))
    db_session.add(BenchmarkRun(user_id=b.id, problem_type="route_planning", payload={}))
    await db_session.commit()

    out = tmp_path / "b.jsonl"
    n = await dump_rows(db_session, "benchmark_runs", out, user_id=a.id)
    assert n == 1
