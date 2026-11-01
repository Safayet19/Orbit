"""Preserve World Bank values with up to 18 fractional digits.

Revision ID: 0002_expand_numeric_precision
Revises: 0001_collection_schema
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0002_expand_numeric_precision"
down_revision: str | None = "0001_collection_schema"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "orbit_records",
        "numeric_value",
        existing_type=sa.Numeric(precision=30, scale=12),
        type_=sa.Numeric(precision=38, scale=18),
        existing_nullable=True,
    )
    op.alter_column(
        "orbit_record_versions",
        "numeric_value",
        existing_type=sa.Numeric(precision=30, scale=12),
        type_=sa.Numeric(precision=38, scale=18),
        existing_nullable=True,
    )


def downgrade() -> None:
    connection = op.get_bind()
    for table_name in ("orbit_records", "orbit_record_versions"):
        high_precision_values = connection.scalar(
            sa.text(
                f'SELECT count(*) FROM "{table_name}" '
                "WHERE numeric_value IS NOT NULL AND scale(numeric_value) > 12"
            )
        )
        if high_precision_values:
            raise RuntimeError(
                "Refusing to reduce numeric precision while high-precision data exists."
            )

    op.alter_column(
        "orbit_records",
        "numeric_value",
        existing_type=sa.Numeric(precision=38, scale=18),
        type_=sa.Numeric(precision=30, scale=12),
        existing_nullable=True,
    )
    op.alter_column(
        "orbit_record_versions",
        "numeric_value",
        existing_type=sa.Numeric(precision=38, scale=18),
        type_=sa.Numeric(precision=30, scale=12),
        existing_nullable=True,
    )
