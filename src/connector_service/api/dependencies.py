"""FastAPI authentication and database dependencies."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from connector_service.config import Settings
from connector_service.core.exceptions import AuthenticationError, AuthorizationError
from connector_service.core.security import digest_opaque_token, secrets_equal
from connector_service.db.models import DashboardSession, Project
from connector_service.db.repositories import authenticate_project


def get_session(request: Request) -> Generator[Session, None, None]:
    with request.app.state.database.session_maker() as session:
        yield session


def require_admin(
    request: Request,
    x_admin_token: Annotated[str | None, Header(alias="X-Admin-Token")] = None,
) -> None:
    settings: Settings = request.app.state.settings
    if x_admin_token is None or not secrets_equal(
        x_admin_token, settings.admin_token.get_secret_value()
    ):
        raise AuthenticationError()


def require_project(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    x_api_key: Annotated[str | None, Header(alias="X-API-Key")] = None,
) -> Project:
    if x_api_key is not None:
        request.state.auth_mode = "api_key"
        return authenticate_project(session, x_api_key)

    plaintext_session = request.cookies.get("connector_dashboard_session")
    if not plaintext_session:
        raise AuthenticationError()
    now = datetime.now(UTC)
    row = session.execute(
        select(DashboardSession, Project)
        .join(Project, Project.id == DashboardSession.project_id)
        .where(
            DashboardSession.token_digest == digest_opaque_token(plaintext_session),
            DashboardSession.revoked_at.is_(None),
            DashboardSession.expires_at > now,
            Project.active.is_(True),
        )
    ).one_or_none()
    if row is None:
        raise AuthenticationError()
    dashboard_session, project = row
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        csrf_cookie = request.cookies.get("connector_dashboard_csrf")
        csrf_header = request.headers.get("X-CSRF-Token")
        if not csrf_cookie or not csrf_header or not secrets_equal(csrf_cookie, csrf_header):
            raise AuthenticationError("A valid dashboard CSRF token is required.")
    dashboard_session.last_used_at = now
    session.commit()
    request.state.auth_mode = "dashboard"
    request.state.dashboard_session_id = dashboard_session.id
    return project


def require_dashboard_project(
    request: Request,
    project: Annotated[Project, Depends(require_project)],
) -> Project:
    if getattr(request.state, "auth_mode", None) != "dashboard":
        raise AuthorizationError("A dashboard session is required for this action.")
    return project
