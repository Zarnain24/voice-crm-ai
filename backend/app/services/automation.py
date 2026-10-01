"""Built-in automation rules.

These run inside the same transaction as the change that triggered them, so the CRM is
never left half-updated. Anything that leaves the system (Slack, n8n) happens afterwards
via the event bus, see `notifier.py`.

| Trigger                     | Rule                                                        |
|-----------------------------|-------------------------------------------------------------|
| New lead with a deal        | Create "Initial outreach" follow-up due today               |
| Deal -> Qualified           | Ensure an open follow-up exists (next business day)         |
| Deal -> Won                 | Close open tasks, create "Kick off onboarding" task         |
| Deal -> Lost                | Close open tasks                                            |
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Contact, Opportunity, Source, Stage, Task, TaskKind, TaskStatus
from .common import add_task, log_activity, next_business_day, today


def on_lead_created(db: Session, contact: Contact, opportunity: Opportunity | None) -> None:
    if opportunity is None:
        return
    add_task(
        db,
        contact=contact,
        opportunity_id=opportunity.id,
        title=f"Initial outreach to {contact.name}",
        due_date=today(),
        source=Source.AUTOMATION,
    )


def on_stage_changed(db: Session, opportunity: Opportunity, new_stage: Stage) -> None:
    contact = opportunity.contact

    if new_stage == Stage.QUALIFIED and not _open_tasks(db, opportunity, TaskKind.FOLLOW_UP):
        add_task(
            db,
            contact=contact,
            opportunity_id=opportunity.id,
            title=f"Follow up with {contact.name}",
            due_date=next_business_day(today()),
            source=Source.AUTOMATION,
        )

    if new_stage in (Stage.WON, Stage.LOST):
        closed = _open_tasks(db, opportunity)
        for task in closed:
            task.status = TaskStatus.DONE
        if closed:
            log_activity(
                db,
                "tasks_closed",
                f"Closed {len(closed)} open task(s) because '{opportunity.title}' is {new_stage}",
                Source.AUTOMATION,
                contact.id,
            )

    if new_stage == Stage.WON:
        add_task(
            db,
            contact=contact,
            opportunity_id=opportunity.id,
            title=f"Kick off onboarding for {contact.company or contact.name}",
            kind=TaskKind.TODO,
            due_date=next_business_day(today()),
            source=Source.AUTOMATION,
        )


def _open_tasks(db: Session, opportunity: Opportunity, kind: TaskKind | None = None) -> list[Task]:
    query = select(Task).where(Task.opportunity_id == opportunity.id, Task.status == TaskStatus.OPEN)
    if kind is not None:
        query = query.where(Task.kind == kind)
    return list(db.scalars(query))
