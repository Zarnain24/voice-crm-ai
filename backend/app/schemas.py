"""Request/response contracts. All input is validated and length-bounded here."""

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from .models import Source, Stage, TaskKind, TaskStatus


class ORM(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------- Contacts ----------
class ContactCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    title: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    company: str | None = Field(default=None, max_length=120)
    # Optionally open a deal in the same call (common "new lead" flow)
    opportunity_title: str | None = Field(default=None, max_length=160)
    opportunity_value: int = Field(default=0, ge=0, le=1_000_000_000)


class ContactOut(ORM):
    id: int
    name: str
    title: str | None
    email: str | None
    phone: str | None
    company: str | None
    created_at: datetime


class ContactMatch(BaseModel):
    contact: ContactOut
    score: float


class ContactResolution(BaseModel):
    """Result of fuzzy name lookup. `confident` means the top match is unambiguous."""

    confident: bool
    matches: list[ContactMatch]


# ---------- Opportunities ----------
class OpportunityCreate(BaseModel):
    contact_id: int
    title: str = Field(min_length=1, max_length=160)
    value: int = Field(default=0, ge=0, le=1_000_000_000)
    stage: Stage = Stage.NEW


class StageUpdate(BaseModel):
    stage: Stage


class OpportunityUpdate(BaseModel):
    """Edit a deal's name and/or value. Stage changes go through StageUpdate so automation runs."""

    title: str | None = Field(default=None, min_length=1, max_length=160)
    value: int | None = Field(default=None, ge=0, le=1_000_000_000)


class OpportunityOut(ORM):
    id: int
    contact_id: int
    contact_name: str
    title: str
    value: int
    stage: Stage
    updated_at: datetime


class PipelineColumn(BaseModel):
    stage: Stage
    count: int
    total_value: int
    opportunities: list[OpportunityOut]


# ---------- Tasks ----------
class TaskCreate(BaseModel):
    contact_id: int
    opportunity_id: int | None = None
    title: str = Field(min_length=1, max_length=200)
    kind: TaskKind = TaskKind.FOLLOW_UP
    due_date: date


class TaskOut(ORM):
    id: int
    contact_id: int
    contact_name: str
    opportunity_id: int | None
    title: str
    kind: TaskKind
    due_date: date
    status: TaskStatus
    source: Source
    created_at: datetime


# ---------- Notes / activity ----------
class NoteCreate(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class ActivityOut(ORM):
    id: int
    contact_id: int | None
    kind: str
    message: str
    source: Source
    created_at: datetime


class ContactDetail(ContactOut):
    opportunities: list[OpportunityOut]
    open_tasks: list[TaskOut]
    recent_activity: list[ActivityOut]


# ---------- Inbound webhook ----------
class InboundLead(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    title: str | None = Field(default=None, max_length=120)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    company: str | None = Field(default=None, max_length=120)
    interest: str | None = Field(default=None, max_length=160)
    estimated_value: int = Field(default=0, ge=0, le=1_000_000_000)


# ---------- Voice ----------
class VoiceTokenOut(BaseModel):
    server_url: str
    token: str
    room: str
    identity: str
