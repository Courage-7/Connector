"""Calendar and Microsoft Teams APIs backed by existing OAuth connections."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session

from connector_service.api.dependencies import get_session, require_project
from connector_service.api.email_connections import active_email_connection
from connector_service.connectors.email.schemas import EmailProvider
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
from connector_service.db.models import Project
from connector_service.providers.catalog import ProviderCatalog

calendar_router = APIRouter(prefix="/v1/connections")
teams_router = APIRouter(prefix="/v1/connections")


@calendar_router.get(
    "/{provider}/{connection_id}/calendar/events",
    response_model=CalendarEventPage,
    tags=["calendar"],
    summary="List upcoming calendar events",
)
async def list_calendar_events(
    provider: EmailProvider,
    connection_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
) -> CalendarEventPage:
    token, client = await _calendar_context(provider, connection_id, request, session, project)
    return await client.list_events(token, limit=limit)


@calendar_router.post(
    "/{provider}/{connection_id}/calendar/events",
    response_model=CalendarEvent,
    status_code=status.HTTP_201_CREATED,
    tags=["calendar"],
    summary="Create a calendar event",
)
async def create_calendar_event(
    provider: EmailProvider,
    connection_id: str,
    body: CalendarEventCreate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> CalendarEvent:
    token, client = await _calendar_context(provider, connection_id, request, session, project)
    return await client.create_event(token, body)


@calendar_router.patch(
    "/{provider}/{connection_id}/calendar/events/{event_id}",
    response_model=CalendarEvent,
    tags=["calendar"],
    summary="Update a calendar event",
)
async def update_calendar_event(
    provider: EmailProvider,
    connection_id: str,
    event_id: str,
    body: CalendarEventUpdate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> CalendarEvent:
    token, client = await _calendar_context(provider, connection_id, request, session, project)
    return await client.update_event(token, event_id, body)


@calendar_router.delete(
    "/{provider}/{connection_id}/calendar/events/{event_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["calendar"],
    summary="Delete a calendar event",
)
async def delete_calendar_event(
    provider: EmailProvider,
    connection_id: str,
    event_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> None:
    token, client = await _calendar_context(provider, connection_id, request, session, project)
    await client.delete_event(token, event_id)


@teams_router.get(
    "/outlook/{connection_id}/teams",
    response_model=list[TeamSummary],
    tags=["Microsoft Teams"],
    summary="List joined Microsoft Teams",
)
async def list_teams(
    connection_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> list[TeamSummary]:
    token, client = await _teams_context(connection_id, request, session, project)
    return await client.list_teams(token)


@teams_router.get(
    "/outlook/{connection_id}/teams/{team_id}/channels",
    response_model=list[ChannelSummary],
    tags=["Microsoft Teams"],
    summary="List channels in a Microsoft Team",
)
async def list_team_channels(
    connection_id: str,
    team_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> list[ChannelSummary]:
    token, client = await _teams_context(connection_id, request, session, project)
    return await client.list_channels(token, team_id)


@teams_router.get(
    "/outlook/{connection_id}/teams/{team_id}/channels/{channel_id}/messages",
    response_model=list[ChannelMessage],
    tags=["Microsoft Teams"],
    summary="List recent channel messages",
)
async def list_team_channel_messages(
    connection_id: str,
    team_id: str,
    channel_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
) -> list[ChannelMessage]:
    token, client = await _teams_context(connection_id, request, session, project)
    return await client.list_channel_messages(token, team_id, channel_id, limit=limit)


@teams_router.post(
    "/outlook/{connection_id}/teams/{team_id}/channels/{channel_id}/messages",
    response_model=ChannelMessage,
    status_code=status.HTTP_201_CREATED,
    tags=["Microsoft Teams"],
    summary="Send a channel message",
)
async def send_team_channel_message(
    connection_id: str,
    team_id: str,
    channel_id: str,
    body: ChannelMessageCreate,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> ChannelMessage:
    token, client = await _teams_context(connection_id, request, session, project)
    return await client.send_channel_message(token, team_id, channel_id, body)


async def _calendar_context(
    provider: EmailProvider,
    connection_id: str,
    request: Request,
    session: Session,
    project: Project,
) -> tuple[str, CalendarClient]:
    _, token, _ = await active_email_connection(
        provider,
        connection_id,
        request,
        session,
        project,
    )
    catalog: ProviderCatalog = request.app.state.providers
    return token, catalog.calendar_client(provider.value)


async def _teams_context(
    connection_id: str,
    request: Request,
    session: Session,
    project: Project,
) -> tuple[str, TeamsClient]:
    _, token, _ = await active_email_connection(
        EmailProvider.OUTLOOK,
        connection_id,
        request,
        session,
        project,
    )
    catalog: ProviderCatalog = request.app.state.providers
    return token, catalog.teams_client()
