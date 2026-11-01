"""Add opaque, server-managed administrator sessions.

Revision ID: 0003_admin_sessions
Revises: 0002_expand_numeric_precision
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0003_admin_sessions"
down_revision: str | None = "0002_expand_numeric_precision"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "orbit_admin_sessions",
        sa.Column("token_hash", sa.String(length=64), primary_key=True, nullable=False),
        sa.Column("csrf_hash", sa.String(length=64), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_orbit_admin_sessions_expires_at",
        "orbit_admin_sessions",
        ["expires_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_orbit_admin_sessions_expires_at",
        table_name="orbit_admin_sessions",
    )
    op.drop_table("orbit_admin_sessions")
