"""CRM REST API: contacts, opportunities, pipeline, tasks, activity."""

from datetime import date

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .. import schemas
from ..database import get_db
from ..models import Activity, Contact, Opportunity, Source, Stage, Task, TaskStatus
from ..security import request_source, require_api_key
from ..services import crm

router = APIRouter(prefix="/api", dependencies=[Depends(require_api_key)])


# ---------- Contacts ----------
@router.get("/contacts", response_model=list[schemas.ContactOut], tags=["contacts"])
def list_contacts(search: str | None = Query(default=None, max_length=120), db: Session = Depends(get_db)):
    query = select(Contact).order_by(Contact.name)
    if search:
        like = f"%{search}%"
        query = query.where(or_(Contact.name.ilike(like), Contact.company.ilike(like), Contact.email.ilike(like)))
    return db.scalars(query).all()


@router.post("/contacts", response_model=schemas.ContactOut, status_code=status.HTTP_201_CREATED, tags=["contacts"])
def create_contact(
    data: schemas.ContactCreate, db: Session = Depends(get_db), source: Source = Depends(request_source)
):
    return crm.create_contact(db, data, source)


@router.get("/contacts/resolve", response_model=schemas.ContactResolution, tags=["contacts"])
def resolve_contact(name: str = Query(min_length=1, max_length=120), db: Session = Depends(get_db)):
    """Fuzzy lookup by spoken name. Used by the voice agent."""
    return crm.resolve_contact(db, name)


@router.get("/contacts/{contact_id}", response_model=schemas.ContactDetail, tags=["contacts"])
def get_contact(contact_id: int, db: Session = Depends(get_db)):
    return crm.contact_detail(db, crm.get_or_404(db, Contact, contact_id))


@router.post("/contacts/{contact_id}/notes", status_code=status.HTTP_204_NO_CONTENT, tags=["contacts"])
def add_note(
    contact_id: int,
    data: schemas.NoteCreate,
    db: Session = Depends(get_db),
    source: Source = Depends(request_source),
):
    crm.add_note(db, crm.get_or_404(db, Contact, contact_id), data.text, source)


# ---------- Opportunities & pipeline ----------
@router.get("/pipeline", response_model=list[schemas.PipelineColumn], tags=["pipeline"])
def get_pipeline(db: Session = Depends(get_db)):
    return crm.pipeline(db)


@router.get("/opportunities", response_model=list[schemas.OpportunityOut], tags=["pipeline"])
def list_opportunities(stage: Stage | None = None, db: Session = Depends(get_db)):
    query = select(Opportunity).order_by(Opportunity.updated_at.desc())
    if stage:
        query = query.where(Opportunity.stage == stage)
    return db.scalars(query).all()


@router.post(
    "/opportunities",
    response_model=schemas.OpportunityOut,
    status_code=status.HTTP_201_CREATED,
    tags=["pipeline"],
)
def create_opportunity(
    data: schemas.OpportunityCreate, db: Session = Depends(get_db), source: Source = Depends(request_source)
):
    return crm.create_opportunity(db, data, source)


@router.patch("/opportunities/{opportunity_id}", response_model=schemas.OpportunityOut, tags=["pipeline"])
def update_opportunity(
    opportunity_id: int,
    data: schemas.OpportunityUpdate,
    db: Session = Depends(get_db),
    source: Source = Depends(request_source),
):
    return crm.update_opportunity(db, crm.get_or_404(db, Opportunity, opportunity_id), data, source)


@router.patch("/opportunities/{opportunity_id}/stage", response_model=schemas.OpportunityOut, tags=["pipeline"])
def update_stage(
    opportunity_id: int,
    data: schemas.StageUpdate,
    db: Session = Depends(get_db),
    source: Source = Depends(request_source),
):
    return crm.change_stage(db, crm.get_or_404(db, Opportunity, opportunity_id), data.stage, source)


# ---------- Tasks ----------
@router.get("/tasks", response_model=list[schemas.TaskOut], tags=["tasks"])
def list_tasks(
    status_: TaskStatus | None = Query(default=None, alias="status"),
    due_on_or_before: date | None = None,
    db: Session = Depends(get_db),
):
    return crm.list_tasks(db, status_, due_on_or_before)


@router.post("/tasks", response_model=schemas.TaskOut, status_code=status.HTTP_201_CREATED, tags=["tasks"])
def create_task(data: schemas.TaskCreate, db: Session = Depends(get_db), source: Source = Depends(request_source)):
    return crm.create_task(db, data, source)


@router.post("/tasks/{task_id}/complete", response_model=schemas.TaskOut, tags=["tasks"])
def complete_task(task_id: int, db: Session = Depends(get_db), source: Source = Depends(request_source)):
    return crm.complete_task(db, crm.get_or_404(db, Task, task_id), source)


# ---------- Activity ----------
@router.get("/activities", response_model=list[schemas.ActivityOut], tags=["activity"])
def list_activities(limit: int = Query(default=30, ge=1, le=200), db: Session = Depends(get_db)):
    return db.scalars(select(Activity).order_by(Activity.id.desc()).limit(limit)).all()
