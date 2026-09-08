"""add benchmark_runs table

Revision ID: d4f1a9c2b8e7
Revises: c65b3aa7b03f
Create Date: 2026-09-02 09:00:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "d4f1a9c2b8e7"
down_revision: Union[str, Sequence[str], None] = "c65b3aa7b03f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "benchmark_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("problem_type", sa.String(length=64), nullable=False),
        sa.Column(
            "payload",
            sa.JSON().with_variant(postgresql.JSONB(astext_type=sa.Text()), "postgresql"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_benchmark_runs_problem_type"), "benchmark_runs", ["problem_type"], unique=False
    )
    op.create_index(
        op.f("ix_benchmark_runs_user_id"), "benchmark_runs", ["user_id"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_benchmark_runs_user_id"), table_name="benchmark_runs")
    op.drop_index(op.f("ix_benchmark_runs_problem_type"), table_name="benchmark_runs")
    op.drop_table("benchmark_runs")
