"""Add persistent scheduling, worker, job, and decision state.

Revision ID: 0004_autonomous_agent
Revises: 0003_admin_sessions

This migration is additive. Existing sources, records, versions, runs, and
administrator sessions are retained.
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0004_autonomous_agent"
down_revision: str | None = "0003_admin_sessions"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None

json_type = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column(
        "orbit_collection_runs",
        sa.Column(
            "quality_status",
            sa.String(length=20),
            server_default="unknown",
            nullable=False,
        ),
    )
    op.add_column(
        "orbit_collection_runs",
        sa.Column(
            "quality_details",
            json_type,
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_orbit_collection_runs_quality_status",
        "orbit_collection_runs",
        "quality_status IN ('healthy', 'degraded', 'failed', 'unknown')",
    )

    op.create_table(
        "orbit_source_schedules",
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("orbit_sources.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("mode", sa.String(length=20), server_default="adaptive", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("base_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("minimum_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("maximum_interval_seconds", sa.Integer(), nullable=False),
        sa.Column("maximum_retries", sa.Integer(), server_default="5", nullable=False),
        sa.Column("priority", sa.Integer(), server_default="5", nullable=False),
        sa.Column("next_due_at", sa.DateTime(timezone=True)),
        sa.Column("last_attempted_at", sa.DateTime(timezone=True)),
        sa.Column("last_successful_at", sa.DateTime(timezone=True)),
        sa.Column("consecutive_failures", sa.Integer(), server_default="0", nullable=False),
        sa.Column("consecutive_unchanged", sa.Integer(), server_default="0", nullable=False),
        sa.Column("health_status", sa.String(length=20), server_default="unknown", nullable=False),
        sa.Column("health_reason", sa.String(length=300)),
        sa.Column("quality_ratio", sa.Float()),
        sa.Column("last_decision", sa.String(length=40)),
        sa.Column("policy_metadata", json_type, server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.CheckConstraint(
            "mode IN ('fixed', 'adaptive', 'paused')",
            name="ck_orbit_source_schedules_mode",
        ),
        sa.CheckConstraint(
            "base_interval_seconds BETWEEN 3600 AND 7776000",
            name="ck_orbit_source_schedules_base_interval",
        ),
        sa.CheckConstraint(
            "minimum_interval_seconds BETWEEN 60 AND 7776000",
            name="ck_orbit_source_schedules_min_interval",
        ),
        sa.CheckConstraint(
            "maximum_interval_seconds BETWEEN 3600 AND 31536000",
            name="ck_orbit_source_schedules_max_interval",
        ),
        sa.CheckConstraint(
            "minimum_interval_seconds <= base_interval_seconds "
            "AND base_interval_seconds <= maximum_interval_seconds",
            name="ck_orbit_source_schedules_interval_order",
        ),
        sa.CheckConstraint(
            "priority BETWEEN 1 AND 10",
            name="ck_orbit_source_schedules_priority",
        ),
    )
    op.create_index(
        "ix_orbit_source_schedules_due",
        "orbit_source_schedules",
        ["enabled", "mode", "next_due_at"],
    )

    op.create_table(
        "orbit_agent_workers",
        sa.Column("id", sa.String(length=120), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("status", sa.String(length=20), server_default="starting", nullable=False),
        sa.Column("active_job_id", sa.Uuid()),
        sa.Column("last_error", sa.String(length=300)),
        sa.Column("version", sa.String(length=40), server_default="0.1.0", nullable=False),
        sa.CheckConstraint(
            "status IN ('starting', 'idle', 'executing', 'stopping', 'unhealthy', 'offline')",
            name="ck_orbit_agent_workers_status",
        ),
    )
    op.create_index(
        "ix_orbit_agent_workers_heartbeat",
        "orbit_agent_workers",
        ["last_heartbeat_at"],
    )

    op.create_table(
        "orbit_agent_jobs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("orbit_sources.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("trigger_type", sa.String(length=20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(length=20), server_default="queued", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("worker_id", sa.String(length=120)),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True)),
        sa.Column("lease_generation", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "collection_run_id",
            sa.Uuid(),
            sa.ForeignKey("orbit_collection_runs.id", ondelete="SET NULL"),
        ),
        sa.Column("failure_category", sa.String(length=40)),
        sa.Column("error_summary", sa.String(length=300)),
        sa.Column("quality_status", sa.String(length=20), server_default="unknown", nullable=False),
        sa.CheckConstraint(
            "trigger_type IN ('manual', 'scheduled')",
            name="ck_orbit_agent_jobs_trigger",
        ),
        sa.CheckConstraint(
            "status IN ('queued', 'running', 'retry_wait', 'completed', 'failed', 'cancelled')",
            name="ck_orbit_agent_jobs_status",
        ),
    )
    op.create_index(
        "ix_orbit_agent_jobs_claim",
        "orbit_agent_jobs",
        ["status", "scheduled_at", "created_at"],
    )
    op.create_index(
        "ix_orbit_agent_jobs_source_created",
        "orbit_agent_jobs",
        ["source_id", "created_at"],
    )
    op.create_index(
        "uq_orbit_agent_jobs_active_source",
        "orbit_agent_jobs",
        ["source_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'running', 'retry_wait')"),
    )

    op.create_table(
        "orbit_agent_decisions",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "source_id",
            sa.Uuid(),
            sa.ForeignKey("orbit_sources.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "job_id",
            sa.Uuid(),
            sa.ForeignKey("orbit_agent_jobs.id", ondelete="SET NULL"),
        ),
        sa.Column("decision_type", sa.String(length=40), nullable=False),
        sa.Column("reason_code", sa.String(length=60), nullable=False),
        sa.Column("explanation", sa.String(length=500), nullable=False),
        sa.Column("context", json_type, server_default=sa.text("'{}'"), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("next_action_at", sa.DateTime(timezone=True)),
        sa.Column("policy_version", sa.String(length=40), server_default="1", nullable=False),
    )
    op.create_index(
        "ix_orbit_agent_decisions_created",
        "orbit_agent_decisions",
        ["created_at"],
    )
    op.create_index(
        "ix_orbit_agent_decisions_source_created",
        "orbit_agent_decisions",
        ["source_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_orbit_agent_decisions_source_created", table_name="orbit_agent_decisions")
    op.drop_index("ix_orbit_agent_decisions_created", table_name="orbit_agent_decisions")
    op.drop_table("orbit_agent_decisions")
    op.drop_index("uq_orbit_agent_jobs_active_source", table_name="orbit_agent_jobs")
    op.drop_index("ix_orbit_agent_jobs_source_created", table_name="orbit_agent_jobs")
    op.drop_index("ix_orbit_agent_jobs_claim", table_name="orbit_agent_jobs")
    op.drop_table("orbit_agent_jobs")
    op.drop_index("ix_orbit_agent_workers_heartbeat", table_name="orbit_agent_workers")
    op.drop_table("orbit_agent_workers")
    op.drop_index("ix_orbit_source_schedules_due", table_name="orbit_source_schedules")
    op.drop_table("orbit_source_schedules")
    op.drop_constraint(
        "ck_orbit_collection_runs_quality_status",
        "orbit_collection_runs",
        type_="check",
    )
    op.drop_column("orbit_collection_runs", "quality_details")
    op.drop_column("orbit_collection_runs", "quality_status")
