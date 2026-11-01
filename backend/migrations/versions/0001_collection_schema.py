"""Create Orbit's collection schema and register the World Bank source.

Revision ID: 0001_collection_schema
Revises:
"""

import uuid
from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0001_collection_schema"
down_revision: str | None = None
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

WORLD_BANK_SOURCE_ID = uuid.UUID("da6f7d8f-50e1-4a0f-a0de-65155268318d")
WORLD_BANK_SOURCE_KEY = "worldbank-bd-inflation"
WORLD_BANK_URL = (
    "https://api.worldbank.org/v2/country/BGD/indicator/FP.CPI.TOTL.ZG"
)


def upgrade() -> None:
    op.create_table(
        "orbit_sources",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("source_key", sa.String(length=120), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("source_type", sa.String(length=40), nullable=False),
        sa.Column("official_url", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=False),
        sa.Column(
            "collection_config",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "licensing_metadata",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("source_key", name="uq_orbit_sources_source_key"),
    )
    op.create_index(
        "ix_orbit_sources_category_enabled",
        "orbit_sources",
        ["category", "enabled"],
    )

    op.create_table(
        "orbit_collection_runs",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "source_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("orbit_sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("records_fetched", sa.Integer(), nullable=False),
        sa.Column("records_new", sa.Integer(), nullable=False),
        sa.Column("records_changed", sa.Integer(), nullable=False),
        sa.Column("records_unchanged", sa.Integer(), nullable=False),
        sa.Column("records_invalid", sa.Integer(), nullable=False),
        sa.Column("error_summary", sa.String(length=300), nullable=True),
        sa.CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_orbit_collection_runs_status",
        ),
        sa.CheckConstraint(
            "records_fetched >= 0 AND records_new >= 0 AND records_changed >= 0 "
            "AND records_unchanged >= 0 AND records_invalid >= 0",
            name="ck_orbit_collection_runs_nonnegative_counts",
        ),
    )
    op.create_index(
        "ix_orbit_collection_runs_source_started",
        "orbit_collection_runs",
        ["source_id", "started_at"],
    )
    op.create_index(
        "ix_orbit_collection_runs_status_started",
        "orbit_collection_runs",
        ["status", "started_at"],
    )

    op.create_table(
        "orbit_records",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "source_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("orbit_sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_record_id", sa.String(length=200), nullable=False),
        sa.Column("category", sa.String(length=120), nullable=False),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("numeric_value", sa.Numeric(precision=30, scale=12), nullable=True),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("first_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.UniqueConstraint(
            "source_id",
            "external_record_id",
            name="uq_orbit_records_source_external",
        ),
    )
    op.create_index(
        "ix_orbit_records_source_category",
        "orbit_records",
        ["source_id", "category"],
    )
    op.create_index(
        "ix_orbit_records_last_observed",
        "orbit_records",
        ["last_observed_at"],
    )

    op.create_table(
        "orbit_record_versions",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "record_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("orbit_records.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column("numeric_value", sa.Numeric(precision=30, scale=12), nullable=True),
        sa.Column("fingerprint", sa.String(length=64), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "provenance",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "record_id",
            "version_number",
            name="uq_orbit_record_versions_number",
        ),
    )
    op.create_index(
        "ix_orbit_record_versions_record_observed",
        "orbit_record_versions",
        ["record_id", "observed_at"],
    )
    op.create_index(
        "ix_orbit_record_versions_fingerprint",
        "orbit_record_versions",
        ["fingerprint"],
    )

    op.create_table(
        "orbit_invalid_records",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True, nullable=False),
        sa.Column(
            "run_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("orbit_collection_runs.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column(
            "source_id",
            sa.Uuid(as_uuid=True),
            sa.ForeignKey("orbit_sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("external_record_id", sa.String(length=200), nullable=True),
        sa.Column(
            "error_details",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_orbit_invalid_records_source_created",
        "orbit_invalid_records",
        ["source_id", "created_at"],
    )
    op.create_index("ix_orbit_invalid_records_run", "orbit_invalid_records", ["run_id"])

    source_table = sa.table(
        "orbit_sources",
        sa.column("id", sa.Uuid(as_uuid=True)),
        sa.column("source_key", sa.String()),
        sa.column("name", sa.String()),
        sa.column("source_type", sa.String()),
        sa.column("official_url", sa.Text()),
        sa.column("category", sa.String()),
        sa.column("collection_config", postgresql.JSONB()),
        sa.column("licensing_metadata", postgresql.JSONB()),
        sa.column("enabled", sa.Boolean()),
    )
    op.bulk_insert(
        source_table,
        [
            {
                "id": WORLD_BANK_SOURCE_ID,
                "source_key": WORLD_BANK_SOURCE_KEY,
                "name": "World Bank Bangladesh Inflation",
                "source_type": "api",
                "official_url": WORLD_BANK_URL,
                "category": "economic_indicators",
                "collection_config": {
                    "country_code": "BGD",
                    "indicator_code": "FP.CPI.TOTL.ZG",
                    "page_size": 1000,
                },
                "licensing_metadata": {
                    "provider": "World Bank",
                    "terms_url": "https://www.worldbank.org/en/about/legal/terms-of-use-for-datasets",
                },
                "enabled": True,
            }
        ],
    )


def downgrade() -> None:
    connection = op.get_bind()
    for table_name in (
        "orbit_record_versions",
        "orbit_records",
        "orbit_collection_runs",
        "orbit_invalid_records",
    ):
        row_count = connection.scalar(sa.text(f'SELECT count(*) FROM "{table_name}"'))
        if row_count:
            raise RuntimeError(
                "Refusing to remove Orbit tables containing collection data."
            )

    other_sources = connection.scalar(
        sa.text(
            "SELECT count(*) FROM orbit_sources WHERE source_key != :source_key"
        ),
        {"source_key": WORLD_BANK_SOURCE_KEY},
    )
    if other_sources:
        raise RuntimeError("Refusing to remove additional registered data sources.")

    op.execute(
        sa.text("DELETE FROM orbit_sources WHERE source_key = :source_key").bindparams(
            source_key=WORLD_BANK_SOURCE_KEY
        )
    )
    op.drop_index("ix_orbit_invalid_records_run", table_name="orbit_invalid_records")
    op.drop_index(
        "ix_orbit_invalid_records_source_created",
        table_name="orbit_invalid_records",
    )
    op.drop_table("orbit_invalid_records")
    op.drop_index(
        "ix_orbit_record_versions_fingerprint",
        table_name="orbit_record_versions",
    )
    op.drop_index(
        "ix_orbit_record_versions_record_observed",
        table_name="orbit_record_versions",
    )
    op.drop_table("orbit_record_versions")
    op.drop_index("ix_orbit_records_last_observed", table_name="orbit_records")
    op.drop_index("ix_orbit_records_source_category", table_name="orbit_records")
    op.drop_table("orbit_records")
    op.drop_index(
        "ix_orbit_collection_runs_status_started",
        table_name="orbit_collection_runs",
    )
    op.drop_index(
        "ix_orbit_collection_runs_source_started",
        table_name="orbit_collection_runs",
    )
    op.drop_table("orbit_collection_runs")
    op.drop_index("ix_orbit_sources_category_enabled", table_name="orbit_sources")
    op.drop_table("orbit_sources")
