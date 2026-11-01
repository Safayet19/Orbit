from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from backend.app.db.models import SourceSchedule

POLICY_VERSION = "1"
MAX_FAILURE_BACKOFF_SECONDS = 6 * 60 * 60
INITIAL_FAILURE_BACKOFF_SECONDS = 5 * 60
MINIMUM_VALID_RATIO = 0.8


class DecisionType(StrEnum):
    COLLECT_NOW = "collect_now"
    POSTPONE = "postpone"
    RETRY_LATER = "retry_later"
    SKIP_ALREADY_RUNNING = "skip_already_running"
    SKIP_DISABLED = "skip_disabled"
    PAUSE_FOR_REVIEW = "pause_for_review"
    ADJUST_INTERVAL = "adjust_interval"
    NO_ACTION = "no_action"


@dataclass(frozen=True)
class Decision:
    decision_type: DecisionType
    reason_code: str
    explanation: str
    next_action_at: datetime | None
    context: dict[str, Any]


@dataclass(frozen=True)
class ScheduleOutcome:
    health_status: str
    health_reason: str
    consecutive_failures: int
    consecutive_unchanged: int
    quality_ratio: float | None
    next_due_at: datetime | None
    decision: Decision


def valid_ratio(fetched: int, invalid: int) -> float | None:
    if fetched <= 0:
        return None
    return max(0.0, min(1.0, (fetched - invalid) / fetched))


def due_decision(
    *,
    source_id: str,
    enabled: bool,
    schedule_enabled: bool,
    mode: str,
    next_due_at: datetime | None,
    now: datetime,
    active_job: bool,
) -> Decision:
    context = {
        "source_id": source_id,
        "enabled": enabled,
        "schedule_enabled": schedule_enabled,
        "mode": mode,
        "next_due_at": next_due_at.isoformat() if next_due_at else None,
        "active_job": active_job,
    }
    if not enabled or not schedule_enabled:
        return Decision(
            DecisionType.SKIP_DISABLED,
            "source_disabled",
            "The source or its schedule is disabled; automatic collection is not permitted.",
            next_due_at,
            context,
        )
    if mode == "paused":
        return Decision(
            DecisionType.POSTPONE,
            "schedule_paused",
            "The schedule is paused by an administrator; no automatic collection was queued.",
            None,
            context,
        )
    if active_job:
        return Decision(
            DecisionType.SKIP_ALREADY_RUNNING,
            "active_job_exists",
            "An active job already exists for this source, so a duplicate was not queued.",
            next_due_at,
            context,
        )
    if next_due_at is not None and next_due_at > now:
        return Decision(
            DecisionType.POSTPONE,
            "not_due",
            "The next permitted collection time has not arrived.",
            next_due_at,
            context,
        )
    return Decision(
        DecisionType.COLLECT_NOW,
        "schedule_due",
        "The approved source is enabled and its persisted schedule is due.",
        now,
        context,
    )


def outcome_decision(
    schedule: SourceSchedule,
    *,
    now: datetime,
    succeeded: bool,
    records_new: int = 0,
    records_changed: int = 0,
    records_invalid: int = 0,
    records_fetched: int = 0,
    retry_after_seconds: float | None = None,
    failure_category: str | None = None,
) -> ScheduleOutcome:
    ratio = valid_ratio(records_fetched, records_invalid)
    failures = schedule.consecutive_failures
    unchanged = schedule.consecutive_unchanged
    maximum_interval = schedule.maximum_interval_seconds
    minimum_interval = schedule.minimum_interval_seconds
    base_interval = schedule.base_interval_seconds

    if not succeeded:
        failures += 1
        retryable = failure_category not in {
            "permission_denied",
            "endpoint_missing",
            "unexpected_response",
            "validation_failure",
            "database_failure",
            "scheduling_configuration",
        }
        if not retryable or failures >= schedule.maximum_retries:
            next_due = None
            health = "degraded"
            reason = (
                "The source requires administrator review after a non-retryable or "
                "repeated failure."
            )
            decision_type = DecisionType.PAUSE_FOR_REVIEW
            reason_code = "retry_limit_or_permanent_failure"
            explanation = (
                f"The last attempt failed ({failure_category or 'worker_failure'}); "
                "automatic retries are stopped pending administrator review."
            )
        else:
            backoff = min(
                INITIAL_FAILURE_BACKOFF_SECONDS * (2 ** min(failures - 1, 10)),
                MAX_FAILURE_BACKOFF_SECONDS,
            )
            if retry_after_seconds is not None:
                backoff = min(
                    max(backoff, int(retry_after_seconds)),
                    MAX_FAILURE_BACKOFF_SECONDS,
                )
            next_due = now + timedelta(seconds=backoff)
            health = "degraded"
            reason = f"The last collection failed ({failure_category or 'worker_failure'})."
            decision_type = DecisionType.RETRY_LATER
            reason_code = "bounded_failure_backoff"
            explanation = (
                f"The collection failed ({failure_category or 'worker_failure'}); "
                f"the next retry is bounded to {backoff} seconds."
            )
        decision = Decision(
            decision_type,
            reason_code,
            explanation,
            next_due,
            {"failure_count": failures, "retry_after_seconds": retry_after_seconds},
        )
        return ScheduleOutcome(
            health,
            reason,
            failures,
            unchanged,
            ratio,
            next_due,
            decision,
        )

    failures = 0
    if ratio is not None and ratio < MINIMUM_VALID_RATIO:
        health = "degraded"
        reason = "Validation quality fell below the 80% accepted-record threshold."
        next_due = now + timedelta(seconds=base_interval)
        decision = Decision(
            DecisionType.PAUSE_FOR_REVIEW,
            "validation_quality_below_threshold",
            "The collection completed, but fewer than 80% of fetched records were valid; "
            "the last known-good dataset was protected and administrator review is recommended.",
            next_due,
            {
                "fetched": records_fetched,
                "invalid": records_invalid,
                "valid_ratio": ratio,
            },
        )
        return ScheduleOutcome(health, reason, failures, 0, ratio, next_due, decision)

    if records_new or records_changed:
        unchanged = 0
        interval = max(minimum_interval, base_interval // 2)
        decision_type = DecisionType.ADJUST_INTERVAL
        reason_code = "meaningful_data_change"
        explanation = (
            "Meaningful observations changed; the next check uses a shorter interval "
            "within the source policy."
        )
    else:
        unchanged += 1
        if schedule.mode == "fixed":
            interval = base_interval
        else:
            interval = min(base_interval * (2 ** min(unchanged, 4)), maximum_interval)
        decision_type = (
            DecisionType.ADJUST_INTERVAL
            if schedule.mode == "adaptive"
            else DecisionType.POSTPONE
        )
        reason_code = "valid_unchanged_observations"
        explanation = (
            "The collection succeeded and observations were valid but unchanged; "
            "the next interval is lengthened only within configured limits."
            if schedule.mode == "adaptive"
            else "The collection succeeded with no meaningful changes; the fixed interval is preserved."
        )
    interval = min(max(interval, minimum_interval), maximum_interval)
    next_due = now + timedelta(seconds=interval)
    decision = Decision(
        decision_type,
        reason_code,
        explanation,
        next_due,
        {
            "records_new": records_new,
            "records_changed": records_changed,
            "records_invalid": records_invalid,
            "valid_ratio": ratio,
            "interval_seconds": interval,
            "consecutive_unchanged": unchanged,
            "policy_version": POLICY_VERSION,
        },
    )
    return ScheduleOutcome(
        "healthy",
        "The collection succeeded and met the configured validation threshold.",
        failures,
        unchanged,
        ratio,
        next_due,
        decision,
    )
