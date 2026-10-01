from datetime import UTC, date, datetime
from enum import StrEnum

from sqlalchemy import Date, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(UTC)


class Stage(StrEnum):
    NEW = "New"
    CONTACTED = "Contacted"
    QUALIFIED = "Qualified"
    PROPOSAL = "Proposal"
    WON = "Won"
    LOST = "Lost"


CLOSED_STAGES = {Stage.WON, Stage.LOST}


class TaskStatus(StrEnum):
    OPEN = "open"
    DONE = "done"


class TaskKind(StrEnum):
    FOLLOW_UP = "follow_up"
    TODO = "todo"


class Source(StrEnum):
    """Who initiated a change. Recorded on every task and activity for auditability."""

    UI = "ui"
    VOICE = "voice"
    AUTOMATION = "automation"
    WEBHOOK = "webhook"


def _enum(e: type[StrEnum]) -> Enum:
    return Enum(e, values_callable=lambda x: [m.value for m in x], native_enum=False)


class Contact(Base):
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    title: Mapped[str | None] = mapped_column(String(120))  # job title
    email: Mapped[str | None] = mapped_column(String(254))
    phone: Mapped[str | None] = mapped_column(String(40))
    company: Mapped[str | None] = mapped_column(String(120))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    opportunities: Mapped[list["Opportunity"]] = relationship(
        back_populates="contact", cascade="all, delete-orphan", order_by="Opportunity.id"
    )
    tasks: Mapped[list["Task"]] = relationship(back_populates="contact", cascade="all, delete-orphan")


class Opportunity(Base):
    __tablename__ = "opportunities"

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(160))
    value: Mapped[int] = mapped_column(Integer, default=0)  # whole dollars
    stage: Mapped[Stage] = mapped_column(_enum(Stage), default=Stage.NEW, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    contact: Mapped[Contact] = relationship(back_populates="opportunities", lazy="joined")
    tasks: Mapped[list["Task"]] = relationship(back_populates="opportunity")

    @property
    def contact_name(self) -> str:
        return self.contact.name


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    opportunity_id: Mapped[int | None] = mapped_column(ForeignKey("opportunities.id", ondelete="SET NULL"))
    title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[TaskKind] = mapped_column(_enum(TaskKind), default=TaskKind.FOLLOW_UP)
    due_date: Mapped[date] = mapped_column(Date, index=True)
    status: Mapped[TaskStatus] = mapped_column(_enum(TaskStatus), default=TaskStatus.OPEN, index=True)
    source: Mapped[Source] = mapped_column(_enum(Source), default=Source.UI)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    contact: Mapped[Contact] = relationship(back_populates="tasks", lazy="joined")
    opportunity: Mapped[Opportunity | None] = relationship(back_populates="tasks")

    @property
    def contact_name(self) -> str:
        return self.contact.name


class Activity(Base):
    """Append-only audit log of everything that happens in the CRM."""

    __tablename__ = "activities"

    id: Mapped[int] = mapped_column(primary_key=True)
    contact_id: Mapped[int | None] = mapped_column(ForeignKey("contacts.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(40))
    message: Mapped[str] = mapped_column(Text)
    source: Mapped[Source] = mapped_column(_enum(Source))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    contact: Mapped[Contact | None] = relationship()
