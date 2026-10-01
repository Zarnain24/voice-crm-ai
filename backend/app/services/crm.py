"""CRM use cases. Routers stay thin; every write goes through here so that auditing,
automation rules and events are applied the same way for the UI, voice agent and webhooks."""

import re
from datetime import date
from difflib import SequenceMatcher

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import schemas
from ..models import Activity, Contact, Opportunity, Source, Stage, Task, TaskKind, TaskStatus
from . import automation
from .common import add_task, commit, emit, log_activity, task_payload


def get_or_404[T](db: Session, model: type[T], obj_id: int) -> T:
    obj = db.get(model, obj_id)
    if obj is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"{model.__name__} {obj_id} not found")
    return obj


# ---------- Contacts ----------
def create_contact(db: Session, data: schemas.ContactCreate, source: Source) -> Contact:
    contact = Contact(
        name=data.name.strip(), title=data.title, email=data.email, phone=data.phone, company=data.company
    )
    db.add(contact)

    opportunity = None
    if data.opportunity_title:
        opportunity = Opportunity(
            contact=contact, title=data.opportunity_title, value=data.opportunity_value, stage=Stage.NEW
        )
        db.add(opportunity)
    db.flush()

    via = f" via {source}" if source != Source.UI else ""
    log_activity(db, "lead_created", f"New lead {contact.name}{via}", source, contact.id)
    emit(
        db,
        "lead.created",
        {
            "contact_id": contact.id,
            "name": contact.name,
            "company": contact.company,
            "email": contact.email,
            "opportunity": opportunity
            and {"id": opportunity.id, "title": opportunity.title, "value": opportunity.value},
            "source": source,
        },
    )
    automation.on_lead_created(db, contact, opportunity)
    commit(db)
    return contact


# Spelling rules that map sound-alike spellings to one form, so speech-to-text variants
# compare equal: "Zarnayn Khaleeq" and "Zarnain Khalique" both become "sarnain kalik".
_SOUND_ALIKE = [
    ("que", "k"),
    ("qu", "k"),
    ("ph", "f"),
    ("ck", "k"),
    ("q", "k"),
    ("c", "k"),
    ("x", "ks"),
    ("z", "s"),
    ("w", "v"),
    ("y", "i"),
    ("ee", "i"),
    ("ea", "i"),
    ("ie", "i"),
    ("oo", "u"),
    ("ou", "u"),
]


def _sound_key(text: str) -> str:
    text = re.sub(r"[^a-z ]", "", text.lower())
    for pattern, replacement in _SOUND_ALIKE:
        text = text.replace(pattern, replacement)
    text = re.sub(r"(?<=\w)h", "", text)  # silent/aspirated h: "khan" -> "kan", "john" -> "jon"
    text = re.sub(r"(\w)\1+", r"\1", text)  # doubled letters: "kaliik" -> "kalik"
    return " ".join(text.split())


def _similarity(query: str, candidate: str) -> float:
    return max(
        SequenceMatcher(None, query.lower(), candidate.lower()).ratio(),
        SequenceMatcher(None, _sound_key(query), _sound_key(candidate)).ratio(),
    )


def resolve_contact(db: Session, name: str, limit: int = 5) -> schemas.ContactResolution:
    """Fuzzy name match, tolerant of speech-to-text errors ("Jon Smyth" -> "John Smith",
    "Zarnayn Khaleeq" -> "Zarnain Khalique")."""
    query = " ".join(name.strip().lower().split())
    scored: list[tuple[float, Contact]] = []
    for contact in db.scalars(select(Contact)):
        full = contact.name.lower()
        score = max(
            _similarity(query, full),
            # Allow first-name-only or last-name-only mentions
            *(_similarity(query, part) * 0.9 for part in full.split()),
        )
        if query in full:
            score = max(score, 0.9)
        if score >= 0.55:
            scored.append((score, contact))

    scored.sort(key=lambda s: s[0], reverse=True)
    matches = [
        schemas.ContactMatch(contact=schemas.ContactOut.model_validate(c), score=round(s, 3)) for s, c in scored[:limit]
    ]
    confident = (
        bool(matches) and matches[0].score >= 0.8 and (len(matches) == 1 or matches[0].score - matches[1].score >= 0.1)
    )
    return schemas.ContactResolution(confident=confident, matches=matches)


def contact_detail(db: Session, contact: Contact) -> schemas.ContactDetail:
    activity = db.scalars(
        select(Activity).where(Activity.contact_id == contact.id).order_by(Activity.id.desc()).limit(10)
    )
    open_tasks = [t for t in contact.tasks if t.status == TaskStatus.OPEN]
    return schemas.ContactDetail(
        **schemas.ContactOut.model_validate(contact).model_dump(),
        opportunities=[schemas.OpportunityOut.model_validate(o) for o in contact.opportunities],
        open_tasks=[schemas.TaskOut.model_validate(t) for t in sorted(open_tasks, key=lambda t: t.due_date)],
        recent_activity=[schemas.ActivityOut.model_validate(a) for a in activity],
    )


def add_note(db: Session, contact: Contact, text: str, source: Source) -> None:
    log_activity(db, "note", text.strip(), source, contact.id)
    emit(db, "note.added", {"contact_id": contact.id, "contact_name": contact.name, "text": text, "source": source})
    commit(db)


# ---------- Opportunities ----------
def create_opportunity(db: Session, data: schemas.OpportunityCreate, source: Source) -> Opportunity:
    contact = get_or_404(db, Contact, data.contact_id)
    opportunity = Opportunity(contact=contact, title=data.title, value=data.value, stage=data.stage)
    db.add(opportunity)
    db.flush()
    log_activity(db, "opportunity_created", f"Opportunity '{data.title}' (${data.value:,}) created", source, contact.id)
    emit(
        db,
        "opportunity.created",
        {
            "opportunity_id": opportunity.id,
            "title": data.title,
            "value": data.value,
            "stage": data.stage,
            "contact_name": contact.name,
            "source": source,
        },
    )
    commit(db)
    return opportunity


def update_opportunity(
    db: Session, opportunity: Opportunity, data: schemas.OpportunityUpdate, source: Source
) -> Opportunity:
    changes = []
    if data.title is not None and data.title != opportunity.title:
        changes.append(f"renamed '{opportunity.title}' → '{data.title}'")
        opportunity.title = data.title
    if data.value is not None and data.value != opportunity.value:
        changes.append(f"value ${opportunity.value:,} → ${data.value:,}")
        opportunity.value = data.value
    if not changes:
        return opportunity

    log_activity(db, "opportunity_updated", f"Deal {', '.join(changes)}", source, opportunity.contact_id)
    emit(
        db,
        "opportunity.updated",
        {
            "opportunity_id": opportunity.id,
            "title": opportunity.title,
            "value": opportunity.value,
            "contact_name": opportunity.contact.name,
            "source": source,
        },
    )
    commit(db)
    return opportunity


def change_stage(db: Session, opportunity: Opportunity, new_stage: Stage, source: Source) -> Opportunity:
    old_stage = opportunity.stage
    if old_stage == new_stage:
        return opportunity

    opportunity.stage = new_stage
    contact = opportunity.contact
    log_activity(db, "stage_changed", f"'{opportunity.title}' moved {old_stage} → {new_stage}", source, contact.id)
    emit(
        db,
        "opportunity.stage_changed",
        {
            "opportunity_id": opportunity.id,
            "title": opportunity.title,
            "value": opportunity.value,
            "contact_id": contact.id,
            "contact_name": contact.name,
            "company": contact.company,
            "from_stage": old_stage,
            "to_stage": new_stage,
            "source": source,
        },
    )
    automation.on_stage_changed(db, opportunity, new_stage)
    commit(db)
    return opportunity


def pipeline(db: Session) -> list[schemas.PipelineColumn]:
    opportunities = db.scalars(select(Opportunity).order_by(Opportunity.updated_at.desc())).all()
    columns = []
    for stage in Stage:
        items = [o for o in opportunities if o.stage == stage]
        columns.append(
            schemas.PipelineColumn(
                stage=stage,
                count=len(items),
                total_value=sum(o.value for o in items),
                opportunities=[schemas.OpportunityOut.model_validate(o) for o in items],
            )
        )
    return columns


# ---------- Tasks ----------
def create_task(db: Session, data: schemas.TaskCreate, source: Source) -> Task:
    contact = get_or_404(db, Contact, data.contact_id)
    if data.opportunity_id is not None:
        opportunity = get_or_404(db, Opportunity, data.opportunity_id)
        if opportunity.contact_id != contact.id:
            raise HTTPException(422, "Opportunity belongs to a different contact")

    # A person asking for a follow-up supersedes the one automation scheduled for the same
    # deal, instead of leaving two competing follow-ups on the board.
    if data.kind == TaskKind.FOLLOW_UP and data.opportunity_id is not None:
        auto = db.scalars(
            select(Task).where(
                Task.opportunity_id == data.opportunity_id,
                Task.kind == TaskKind.FOLLOW_UP,
                Task.status == TaskStatus.OPEN,
                Task.source == Source.AUTOMATION,
            )
        ).first()
        if auto is not None:
            auto.title, auto.due_date, auto.source = data.title, data.due_date, source
            log_activity(
                db,
                "task_rescheduled",
                f"Follow-up updated to '{data.title}' due {data.due_date:%a %b %d}",
                source,
                contact.id,
            )
            emit(db, "task.updated", task_payload(auto))
            commit(db)
            return auto

    task = add_task(
        db,
        contact=contact,
        opportunity_id=data.opportunity_id,
        title=data.title,
        kind=data.kind,
        due_date=data.due_date,
        source=source,
    )
    commit(db)
    return task


def complete_task(db: Session, task: Task, source: Source) -> Task:
    if task.status == TaskStatus.DONE:
        return task
    task.status = TaskStatus.DONE
    log_activity(db, "task_completed", f"Completed '{task.title}'", source, task.contact_id)
    emit(db, "task.completed", task_payload(task))
    commit(db)
    return task


def list_tasks(db: Session, status_: TaskStatus | None, due_on_or_before: date | None) -> list[Task]:
    query = select(Task).order_by(Task.due_date, Task.id)
    if status_ is not None:
        query = query.where(Task.status == status_)
    if due_on_or_before is not None:
        query = query.where(Task.due_date <= due_on_or_before)
    return list(db.scalars(query))
