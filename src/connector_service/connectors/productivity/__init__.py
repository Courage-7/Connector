"""Shared contracts for calendar and Microsoft Teams providers."""

from connector_service.connectors.productivity.base import CalendarClient, TeamsClient
from connector_service.connectors.productivity.schemas import (
    CalendarEvent,
    CalendarEventCreate,
    CalendarEventPage,
    CalendarEventUpdate,
    ChannelMessage,
    ChannelMessageCreate,
    ChannelSummary,
    TeamSummary,
)

__all__ = [
    "CalendarClient",
    "CalendarEvent",
    "CalendarEventCreate",
    "CalendarEventPage",
    "CalendarEventUpdate",
    "ChannelMessage",
    "ChannelMessageCreate",
    "ChannelSummary",
    "TeamSummary",
    "TeamsClient",
]
