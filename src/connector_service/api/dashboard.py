"""Opaque browser-session handoff for the connector dashboard."""

from __future__ import annotations

import secrets
from datetime import UTC, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status
from fastapi.responses import RedirectResponse
from pydantic import Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from connector_service.api.dependencies import get_session, require_project
from connector_service.config import Settings
from connector_service.core.contracts import StrictModel
from connector_service.core.exceptions import AuthenticationError, InvalidRequestError
from connector_service.core.security import create_opaque_token, digest_opaque_token
from connector_service.db.models import DashboardLoginTicket, DashboardSession, Project

router = APIRouter(prefix="/v1/dashboard", tags=["dashboard"])


class LoginTicketResponse(StrictModel):
    ticket: str
    login_url: str
    expires_at: datetime


class DashboardProject(StrictModel):
    id: str
    name: str


class DashboardSessionResponse(StrictModel):
    project: DashboardProject
    expires_at: datetime


class LoginTicketOptions(StrictModel):
    return_to: str = Field(default="/app/", pattern=r"^/app/?$")


@router.post("/login-tickets", response_model=LoginTicketResponse)
def create_login_ticket(
    body: LoginTicketOptions,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> LoginTicketResponse:
    settings: Settings = request.app.state.settings
    plaintext, token_digest = create_opaque_token()
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.dashboard_login_ticket_ttl_seconds)
    session.add(
        DashboardLoginTicket(
            project_id=project.id,
            token_digest=token_digest,
            expires_at=expires_at,
        )
    )
    session.commit()
    exchange_url = request.url_for("exchange_login_ticket").include_query_params(
        ticket=plaintext,
        return_to=body.return_to,
    )
    return LoginTicketResponse(
        ticket=plaintext,
        login_url=str(exchange_url),
        expires_at=expires_at,
    )


@router.get("/session/exchange", name="exchange_login_ticket")
def exchange_login_ticket(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    ticket: Annotated[str, Query(min_length=32, max_length=256)],
    return_to: Annotated[str, Query(pattern=r"^/app/?$")] = "/app/",
) -> RedirectResponse:
    now = datetime.now(UTC)
    stored_ticket = session.scalar(
        select(DashboardLoginTicket)
        .where(
            DashboardLoginTicket.token_digest == digest_opaque_token(ticket),
            DashboardLoginTicket.consumed_at.is_(None),
            DashboardLoginTicket.expires_at > now,
        )
        .with_for_update()
    )
    if stored_ticket is None:
        raise InvalidRequestError("The dashboard login ticket is invalid or expired.")
    plaintext_session, session_digest = create_opaque_token()
    settings: Settings = request.app.state.settings
    expires_at = now + timedelta(seconds=settings.dashboard_session_ttl_seconds)
    stored_ticket.consumed_at = now
    session.add(
        DashboardSession(
            project_id=stored_ticket.project_id,
            token_digest=session_digest,
            expires_at=expires_at,
            last_used_at=now,
        )
    )
    session.commit()

    response = RedirectResponse(return_to, status_code=status.HTTP_303_SEE_OTHER)
    secure_cookie = settings.environment == "production"
    response.set_cookie(
        "connector_dashboard_session",
        plaintext_session,
        max_age=settings.dashboard_session_ttl_seconds,
        httponly=True,
        secure=secure_cookie,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        "connector_dashboard_csrf",
        secrets.token_urlsafe(24),
        max_age=settings.dashboard_session_ttl_seconds,
        httponly=False,
        secure=secure_cookie,
        samesite="strict",
        path="/",
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Referrer-Policy"] = "no-referrer"
    return response


@router.get("/session", response_model=DashboardSessionResponse)
def get_dashboard_session(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> DashboardSessionResponse:
    session_id = getattr(request.state, "dashboard_session_id", None)
    if not isinstance(session_id, str):
        raise AuthenticationError("A dashboard session is required.")
    dashboard_session = session.get(DashboardSession, session_id)
    if dashboard_session is None:
        raise AuthenticationError()
    return DashboardSessionResponse(
        project=DashboardProject(id=project.id, name=project.name),
        expires_at=dashboard_session.expires_at,
    )


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
def revoke_dashboard_session(
    request: Request,
    response: Response,
    session: Annotated[Session, Depends(get_session)],
    _project: Annotated[Project, Depends(require_project)],
) -> None:
    session_id = getattr(request.state, "dashboard_session_id", None)
    if isinstance(session_id, str):
        dashboard_session = session.get(DashboardSession, session_id)
        if dashboard_session is not None:
            dashboard_session.revoked_at = datetime.now(UTC)
            session.commit()
    response.delete_cookie("connector_dashboard_session", path="/")
    response.delete_cookie("connector_dashboard_csrf", path="/")
