"""Add review_schedule table for spaced repetition and weak topic tracking.

Revision ID: 0002_review_schedule
Revises: 0001_initial_schema
Create Date: 2026-10-14
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "0002_review_schedule"
down_revision: str | None = "0001_initial_schema"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "review_schedule",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("session_id", sa.Uuid(), nullable=False),
        sa.Column("topic", sa.String(length=100), nullable=False),
        sa.Column("reason", sa.String(length=255), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("repetition_number", sa.Integer(), server_default="0", nullable=False),
        sa.Column("interval_days", sa.Integer(), server_default="1", nullable=False),
        sa.Column("ease_factor", sa.Float(), server_default="2.5", nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint("interval_days >= 1", name="chk_review_interval"),
        sa.CheckConstraint("ease_factor >= 1.3", name="chk_review_ease_factor"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_schedule_user_id", "review_schedule", ["user_id"], unique=False)
    op.create_index(
        "ix_review_schedule_session_id", "review_schedule", ["session_id"], unique=False
    )
    op.create_index("ix_review_schedule_status", "review_schedule", ["status"], unique=False)
    op.create_index(
        "ix_review_schedule_user_status", "review_schedule", ["user_id", "status"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_review_schedule_user_status", table_name="review_schedule")
    op.drop_index("ix_review_schedule_status", table_name="review_schedule")
    op.drop_index("ix_review_schedule_session_id", table_name="review_schedule")
    op.drop_index("ix_review_schedule_user_id", table_name="review_schedule")
    op.drop_table("review_schedule")
