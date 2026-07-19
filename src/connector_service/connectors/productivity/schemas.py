"""Strict normalized contracts for calendar and Microsoft Teams operations."""

from __future__ import annotations

from datetime import datetime

from pydantic import Field, field_validator, model_validator

from connector_service.connectors.email.schemas import validate_email_address
from connector_service.core.contracts import StrictModel


class CalendarEventCreate(StrictModel):
    title: str = Field(min_length=1, max_length=500)
    start: datetime
    end: datetime
    timezone: str = Field(default="UTC", min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=50_000)
    location: str | None = Field(default=None, max_length=500)
    attendees: list[str] = Field(default_factory=list, max_length=50)

    @field_validator("attendees")
    @classmethod
    def validate_attendees(cls, values: list[str]) -> list[str]:
        normalized = [validate_email_address(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("attendees must not contain duplicates")
        return normalized

    @model_validator(mode="after")
    def validate_times(self) -> CalendarEventCreate:
        if (self.start.tzinfo is None) != (self.end.tzinfo is None):
            raise ValueError("start and end must use the same timezone style")
        if self.end <= self.start:
            raise ValueError("end must be after start")
        return self


class CalendarEventUpdate(StrictModel):
    title: str | None = Field(default=None, min_length=1, max_length=500)
    start: datetime | None = None
    end: datetime | None = None
    timezone: str | None = Field(default=None, min_length=1, max_length=100)
    description: str | None = Field(default=None, max_length=50_000)
    location: str | None = Field(default=None, max_length=500)
    attendees: list[str] | None = Field(default=None, max_length=50)

    @field_validator("attendees")
    @classmethod
    def validate_attendees(cls, values: list[str] | None) -> list[str] | None:
        if values is None:
            return None
        normalized = [validate_email_address(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("attendees must not contain duplicates")
        return normalized

    @model_validator(mode="after")
    def validate_update(self) -> CalendarEventUpdate:
        if not self.model_fields_set:
            raise ValueError("at least one event field is required")
        if self.timezone is not None and self.start is None and self.end is None:
            raise ValueError("timezone requires start or end")
        if self.start is not None and self.end is not None:
            if (self.start.tzinfo is None) != (self.end.tzinfo is None):
                raise ValueError("start and end must use the same timezone style")
            if self.end <= self.start:
                raise ValueError("end must be after start")
        return self


class CalendarEvent(StrictModel):
    id: str
    title: str
    start: datetime | None = None
    end: datetime | None = None
    timezone: str | None = None
    description: str | None = None
    location: str | None = None
    attendees: list[str] = Field(default_factory=list)
    web_url: str | None = None


class CalendarEventPage(StrictModel):
    data: list[CalendarEvent]
    returned: int


class TeamSummary(StrictModel):
    id: str
    name: str
    description: str | None = None


class ChannelSummary(StrictModel):
    id: str
    name: str
    description: str | None = None


class ChannelMessageCreate(StrictModel):
    content: str = Field(min_length=1, max_length=20_000)


class ChannelMessage(StrictModel):
    id: str
    content: str = Field(max_length=100_000)
    sender: str | None = None
    created_at: datetime | None = None
    web_url: str | None = None
