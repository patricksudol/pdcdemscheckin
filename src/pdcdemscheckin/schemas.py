from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from .models import MeetingStatus, OrganizerRole


class ApiModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class EmailLookup(ApiModel):
    email: EmailStr


class ProfileCreate(ApiModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=30)
    consent: bool

    @field_validator("consent")
    @classmethod
    def require_consent(cls, value: bool) -> bool:
        if not value:
            raise ValueError("Consent is required to create a profile")
        return value


class ExistingCheckin(ApiModel):
    email: EmailStr


class MeetingCreate(ApiModel):
    title: str = Field(min_length=1, max_length=180)
    starts_at: datetime
    location: str | None = Field(default=None, max_length=240)
    attendee_message: str | None = Field(default=None, max_length=2000)


class MeetingUpdate(ApiModel):
    title: str | None = Field(default=None, min_length=1, max_length=180)
    starts_at: datetime | None = None
    location: str | None = Field(default=None, max_length=240)
    attendee_message: str | None = Field(default=None, max_length=2000)


class MeetingStatusUpdate(ApiModel):
    status: MeetingStatus


class ProfileUpdate(ApiModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)


class AdminProfileCreate(ApiModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=30)


class ManualCheckin(ApiModel):
    profile_id: UUID
    reason: str = Field(min_length=3, max_length=500)


class CorrectionReason(ApiModel):
    reason: str = Field(min_length=3, max_length=500)


class MergeProfiles(ApiModel):
    source_profile_id: UUID
    target_profile_id: UUID
    reason: str = Field(min_length=3, max_length=500)


class OrganizerCreate(ApiModel):
    email: EmailStr
    display_name: str = Field(min_length=1, max_length=180)
    role: OrganizerRole = OrganizerRole.admin


class OrganizerUpdate(ApiModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=180)
    role: OrganizerRole | None = None
    active: bool | None = None


class PasswordSet(ApiModel):
    password: str = Field(min_length=12, max_length=128)


class PasswordChange(PasswordSet):
    current_password: str = Field(min_length=1, max_length=128)


class OneTapBackfill(ApiModel):
    dry_run: bool = True
    confirm: bool = False
