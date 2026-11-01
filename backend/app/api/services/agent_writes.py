from datetime import timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.agents.decision_engine import Decision, DecisionType
from backend.app.api.schemas import AgentScheduleUpdate
from backend.app.collectors.worldbank import INDICATORS_BY_SOURCE
from backend.app.db.models import AgentDecision, Source, SourceSchedule, utc_now


class AgentScheduleError(ValueError):
    pass


def _decision(
    session: Session,
    source_id: Any,
    decision_type: DecisionType,
    reason_code: str,
    explanation: str,
    context: dict[str, Any],
    next_action_at: Any = None,
) -> None:
    session.add(
        AgentDecision(
            source_id=source_id,
            decision_type=decision_type.value,
            reason_code=reason_code,
            explanation=explanation,
            context=context,
            next_action_at=next_action_at,
        )
    )


def update_schedule(
    session: Session,
    source_key: str,
    changes: AgentScheduleUpdate,
) -> SourceSchedule:
    row = session.execute(
        select(Source, SourceSchedule)
        .join(SourceSchedule, SourceSchedule.source_id == Source.id)
        .where(Source.source_key == source_key)
        .with_for_update()
    ).first()
    if row is None:
        raise AgentScheduleError("Source schedule was not found.")
    source, schedule = row
    if source_key not in INDICATORS_BY_SOURCE:
        raise AgentScheduleError("No approved collector is registered for this source.")
    if not source.enabled:
        raise AgentScheduleError("Disabled sources cannot be scheduled.")

    previous_mode = schedule.mode
    values = changes.model_dump(exclude_unset=True)
    if not values:
        raise AgentScheduleError("At least one scheduling setting must be provided.")
    for key, value in values.items():
        if value is not None:
            setattr(schedule, key, value)
    if not (
        schedule.minimum_interval_seconds
        <= schedule.base_interval_seconds
        <= schedule.maximum_interval_seconds
    ):
        raise AgentScheduleError(
            "Schedule intervals must satisfy minimum <= base <= maximum."
        )
    now = utc_now()
    if schedule.mode == "paused":
        if previous_mode != "paused":
            schedule.policy_metadata = {
                **schedule.policy_metadata,
                "resume_mode": previous_mode,
            }
        schedule.next_due_at = None
    elif previous_mode == "paused" and schedule.enabled:
        schedule.next_due_at = now
    elif not schedule.enabled:
        schedule.next_due_at = None
    schedule.health_status = (
        "paused" if schedule.mode == "paused" or not schedule.enabled else schedule.health_status
    )
    schedule.updated_at = now
    _decision(
        session,
        source.id,
        DecisionType.ADJUST_INTERVAL,
        "administrator_policy_update",
        "An authenticated administrator updated the source scheduling policy.",
        {"source_id": source_key, "changes": values},
        schedule.next_due_at,
    )
    schedule.last_decision = DecisionType.ADJUST_INTERVAL.value
    return schedule


def pause_schedule(session: Session, source_key: str) -> SourceSchedule:
    row = session.execute(
        select(Source, SourceSchedule)
        .join(SourceSchedule, SourceSchedule.source_id == Source.id)
        .where(Source.source_key == source_key)
        .with_for_update()
    ).first()
    if row is None:
        raise AgentScheduleError("Source schedule was not found.")
    source, schedule = row
    if source_key not in INDICATORS_BY_SOURCE:
        raise AgentScheduleError("No approved collector is registered for this source.")
    if schedule.mode != "paused":
        schedule.policy_metadata = {
            **schedule.policy_metadata,
            "resume_mode": schedule.mode,
        }
    schedule.mode = "paused"
    schedule.next_due_at = None
    schedule.health_status = "paused"
    schedule.health_reason = "An administrator paused automatic collection."
    schedule.updated_at = utc_now()
    schedule.last_decision = DecisionType.POSTPONE.value
    _decision(
        session,
        source.id,
        DecisionType.POSTPONE,
        "administrator_paused_schedule",
        "An authenticated administrator paused future automatic collection.",
        {"source_id": source_key},
    )
    return schedule


def resume_schedule(session: Session, source_key: str) -> SourceSchedule:
    row = session.execute(
        select(Source, SourceSchedule)
        .join(SourceSchedule, SourceSchedule.source_id == Source.id)
        .where(Source.source_key == source_key)
        .with_for_update()
    ).first()
    if row is None:
        raise AgentScheduleError("Source schedule was not found.")
    source, schedule = row
    if source_key not in INDICATORS_BY_SOURCE:
        raise AgentScheduleError("No approved collector is registered for this source.")
    if not source.enabled or not schedule.enabled:
        raise AgentScheduleError(
            "The source or schedule is disabled; enable it before resuming."
        )
    if schedule.mode == "paused":
        previous_mode = schedule.policy_metadata.get("resume_mode")
        schedule.mode = previous_mode if previous_mode in {"fixed", "adaptive"} else "adaptive"
    now = utc_now()
    schedule.next_due_at = now
    schedule.health_status = "unknown"
    schedule.health_reason = None
    schedule.updated_at = now
    schedule.last_decision = DecisionType.COLLECT_NOW.value
    _decision(
        session,
        source.id,
        DecisionType.COLLECT_NOW,
        "administrator_resumed_schedule",
        "An authenticated administrator resumed the source schedule; the next check is due now.",
        {"source_id": source_key, "mode": schedule.mode},
        now,
    )
    return schedule
