"""Provider-neutral protocols for calendar and Teams operations."""

from __future__ import annotations

from typing import Protocol

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


class CalendarClient(Protocol):
    async def list_events(self, access_token: str, *, limit: int) -> CalendarEventPage: ...

    async def create_event(
        self,
        access_token: str,
        event: CalendarEventCreate,
    ) -> CalendarEvent: ...

    async def update_event(
        self,
        access_token: str,
        event_id: str,
        event: CalendarEventUpdate,
    ) -> CalendarEvent: ...

    async def delete_event(self, access_token: str, event_id: str) -> None: ...


class TeamsClient(Protocol):
    async def list_teams(self, access_token: str) -> list[TeamSummary]: ...

    async def list_channels(
        self,
        access_token: str,
        team_id: str,
    ) -> list[ChannelSummary]: ...

    async def list_channel_messages(
        self,
        access_token: str,
        team_id: str,
        channel_id: str,
        *,
        limit: int,
    ) -> list[ChannelMessage]: ...

    async def send_channel_message(
        self,
        access_token: str,
        team_id: str,
        channel_id: str,
        message: ChannelMessageCreate,
    ) -> ChannelMessage: ...
