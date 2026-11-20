"""add review_reports table

Revision ID: e9b1b3948ff3
Revises: 711eae64c1cd
Create Date: 2026-11-20 16:57:45.271948

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e9b1b3948ff3"
down_revision: str | Sequence[str] | None = "711eae64c1cd"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # NOTE: autogen diffed the FTS5 shadow tables — they're virtual-table
    # internals, not metadata; only review_reports is real work here.
    op.create_table(
        "review_reports",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("report_id", sa.String(length=64), nullable=False),
        sa.Column("agent", sa.String(length=64), nullable=False),
        sa.Column("kind", sa.String(length=32), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("trace_id", sa.String(length=64), nullable=False),
        sa.Column("ts", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_review_reports_agent"), "review_reports", ["agent"], unique=False
    )
    op.create_index(
        op.f("ix_review_reports_report_id"),
        "review_reports",
        ["report_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_review_reports_trace_id"),
        "review_reports",
        ["trace_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_review_reports_trace_id"), table_name="review_reports")
    op.drop_index(op.f("ix_review_reports_report_id"), table_name="review_reports")
    op.drop_index(op.f("ix_review_reports_agent"), table_name="review_reports")
    op.drop_table("review_reports")
