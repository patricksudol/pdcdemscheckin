from __future__ import annotations

import enum
import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utcnow() -> datetime:
    return datetime.now(UTC)


class Base(DeclarativeBase):
    pass


class MeetingStatus(enum.StrEnum):
    draft = "draft"
    open = "open"
    closed = "closed"


class OrganizerRole(enum.StrEnum):
    owner = "owner"
    admin = "admin"


class CheckinSource(enum.StrEnum):
    self_service = "self"
    admin = "admin"


class Profile(Base):
    __tablename__ = "profiles"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    first_name: Mapped[str] = mapped_column(String(100))
    last_name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str | None] = mapped_column(String(320))
    normalized_email: Mapped[str | None] = mapped_column(String(320), unique=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(30))
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    checkins: Mapped[list[Checkin]] = relationship(back_populates="profile")


class Meeting(Base):
    __tablename__ = "meetings"
    __table_args__ = (
        Index(
            "uq_meetings_one_open",
            "status",
            unique=True,
            postgresql_where=text("status = 'open'"),
            sqlite_where=text("status = 'open'"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String(180))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    location: Mapped[str | None] = mapped_column(String(240))
    attendee_message: Mapped[str | None] = mapped_column(Text)
    status: Mapped[MeetingStatus] = mapped_column(
        Enum(MeetingStatus, native_enum=False), default=MeetingStatus.draft, index=True
    )
    public_token: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizers.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    checkins: Mapped[list[Checkin]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan"
    )


class Organizer(Base):
    __tablename__ = "organizers"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    password_hash: Mapped[str | None] = mapped_column(String(255))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    display_name: Mapped[str] = mapped_column(String(180))
    role: Mapped[OrganizerRole] = mapped_column(
        Enum(OrganizerRole, native_enum=False), default=OrganizerRole.admin
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class Checkin(Base):
    __tablename__ = "checkins"
    __table_args__ = (
        UniqueConstraint("meeting_id", "profile_id", name="uq_checkin_meeting_profile"),
        Index("ix_checkins_meeting_checked_at", "meeting_id", "checked_in_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    meeting_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("meetings.id", ondelete="CASCADE"))
    profile_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("profiles.id", ondelete="SET NULL")
    )
    checked_in_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source: Mapped[CheckinSource] = mapped_column(
        Enum(CheckinSource, native_enum=False), default=CheckinSource.self_service
    )
    corrected_by_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizers.id"))
    anonymized_name: Mapped[str | None] = mapped_column(String(200))

    meeting: Mapped[Meeting] = relationship(back_populates="checkins")
    profile: Mapped[Profile | None] = relationship(back_populates="checkins")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("organizers.id"))
    action: Mapped[str] = mapped_column(String(80), index=True)
    entity_type: Mapped[str] = mapped_column(String(80))
    entity_id: Mapped[str] = mapped_column(String(64))
    reason: Mapped[str | None] = mapped_column(String(500))
    before: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    request_id: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
