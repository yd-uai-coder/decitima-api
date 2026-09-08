"""benchmark_runs / solutions を JSONL にエクスポートする(分析の入力)。

使い方:
    python -m analysis.export benchmark_runs analysis/data/benchmark_runs.jsonl
    python -m analysis.export solutions      analysis/data/solutions.jsonl --user <uuid>

1 行 1 JSON(JSONL)。uuid / datetime は文字列化する。notebook / テスト / CI は
この出力ファイルを読む(ライブ DB 不要・再現可能)。
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from analysis.db import session_scope
from app.core.database import Base
from app.models.optimization import BenchmarkRun, Solution

_TABLES: dict[str, type[Base]] = {
    "benchmark_runs": BenchmarkRun,
    "solutions": Solution,
}


def _row_to_dict(row: Base) -> dict:
    """ORM 行を JSON 可能な dict に(uuid / datetime → str)。"""
    raw = {c.name: getattr(row, c.name) for c in row.__table__.columns}
    return json.loads(json.dumps(raw, default=str))


async def dump_rows(
    session: AsyncSession, table: str, out_path: Path, *, user_id: uuid.UUID | None = None
) -> int:
    """渡された session から table の行を取り、JSONL に書く。書いた行数を返す。"""
    model = _TABLES[table]
    stmt = select(model)
    if user_id is not None and hasattr(model, "user_id"):
        stmt = stmt.where(model.user_id == user_id)
    rows = (await session.execute(stmt)).scalars().all()

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(_row_to_dict(row), ensure_ascii=False) + "\n")
    return len(rows)


async def export_table(table: str, out_path: Path, *, user_id: uuid.UUID | None = None) -> int:
    """`session_scope()` で開いた実 DB から `dump_rows` する CLI 用ラッパ。"""
    async with session_scope() as session:
        return await dump_rows(session, table, out_path, user_id=user_id)


def _main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[0] not in _TABLES:
        print(f"usage: python -m analysis.export <{'|'.join(_TABLES)}> <out.jsonl> [--user <uuid>]")
        return 2
    table, out = argv[0], Path(argv[1])
    user = uuid.UUID(argv[argv.index("--user") + 1]) if "--user" in argv else None
    n = asyncio.run(export_table(table, out, user_id=user))
    print(f"wrote {n} rows to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(_main(sys.argv[1:]))
