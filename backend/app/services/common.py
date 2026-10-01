"""Shared helpers for the service layer: dates, audit log and post-commit events."""

from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from ..config import get_settings
from ..events import bus
from ..models import Activity, Contact, Source, Task, TaskKind

_PENDING = "pending_events"


def today() -> date:
    """'Today' in the business timezone, not the server's."""
    return datetime.now(ZoneInfo(get_settings().app_timezone)).date()


def next_business_day(start: date) -> date:
    day = start + timedelta(days=1)
    while day.weekday() >= 5:  # Sat/Sun
        day += timedelta(days=1)
    return day


def log_activity(db: Session, kind: str, message: str, source: Source, contact_id: int | None) -> None:
    db.add(Activity(kind=kind, message=message, source=source, contact_id=contact_id))


def add_task(
    db: Session,
    *,
    contact: Contact,
    title: str,
    due_date: date,
    source: Source,
    kind: TaskKind = TaskKind.FOLLOW_UP,
    opportunity_id: int | None = None,
) -> Task:
    task = Task(
        contact=contact, opportunity_id=opportunity_id, title=title, kind=kind, due_date=due_date, source=source
    )
    db.add(task)
    db.flush()
    log_activity(db, "task_created", f"Task '{title}' due {due_date:%a %b %d}", source, contact.id)
    emit(db, "task.created", task_payload(task))
    return task


def task_payload(task: Task) -> dict[str, Any]:
    return {
        "task_id": task.id,
        "title": task.title,
        "kind": task.kind,
        "due_date": task.due_date.isoformat(),
        "status": task.status,
        "source": task.source,
        "contact_id": task.contact_id,
        "contact_name": task.contact.name,
        "opportunity_id": task.opportunity_id,
    }


def emit(db: Session, event_type: str, data: dict[str, Any]) -> None:
    """Queue an event on the session; it is only published if the transaction commits."""
    db.info.setdefault(_PENDING, []).append((event_type, data))


def commit(db: Session) -> None:
    db.commit()
    for event_type, data in db.info.pop(_PENDING, []):
        bus.publish(event_type, data)
