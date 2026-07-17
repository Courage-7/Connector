"""Narrow database operations used by HTTP dependencies and routes."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from connector_service.core.exceptions import (
    AuthenticationError,
    InvalidRequestError,
    NotFoundError,
)
from connector_service.core.security import ApiKeyManager
from connector_service.db.models import (
    ConnectorGrant,
    Credential,
    OAuthAttempt,
    Project,
    ProjectApiKey,
    ProviderConnection,
)


def get_project(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise NotFoundError("The requested project was not found.")
    return project


def get_credential(session: Session, credential_id: str) -> Credential:
    credential = session.get(Credential, credential_id)
    if credential is None:
        raise NotFoundError("The requested credential was not found.")
    return credential


def get_grant_for_project(session: Session, grant_id: str, project_id: str) -> ConnectorGrant:
    grant = session.scalar(
        select(ConnectorGrant).where(
            ConnectorGrant.id == grant_id,
            ConnectorGrant.project_id == project_id,
            ConnectorGrant.active.is_(True),
        )
    )
    if grant is None:
        raise NotFoundError("The requested connector grant was not found.")
    return grant


def authenticate_project(session: Session, plaintext_key: str) -> Project:
    prefix, secret = ApiKeyManager.parse(plaintext_key)
    row = session.execute(
        select(ProjectApiKey, Project)
        .join(Project, Project.id == ProjectApiKey.project_id)
        .where(
            ProjectApiKey.prefix == prefix,
            ProjectApiKey.active.is_(True),
            Project.active.is_(True),
        )
    ).one_or_none()
    if row is None:
        raise AuthenticationError()
    api_key, project = row
    if not ApiKeyManager.verify(secret, api_key.salt, api_key.digest):
        raise AuthenticationError()
    api_key.last_used_at = datetime.now(UTC)
    session.commit()
    return project


def consume_oauth_attempt(
    session: Session,
    *,
    state_digest: bytes,
    connector: str,
) -> OAuthAttempt:
    now = datetime.now(UTC)
    attempt = session.scalar(
        select(OAuthAttempt)
        .where(
            OAuthAttempt.state_digest == state_digest,
            OAuthAttempt.connector == connector,
            OAuthAttempt.consumed_at.is_(None),
            OAuthAttempt.expires_at > now,
        )
        .with_for_update()
    )
    if attempt is None:
        raise InvalidRequestError("The OAuth state is invalid, expired, or already used.")
    attempt.consumed_at = now
    session.commit()
    return attempt


def get_connection_for_project(
    session: Session,
    *,
    connection_id: str,
    project_id: str,
    connector: str = "supabase",
) -> ProviderConnection:
    connection = session.scalar(
        select(ProviderConnection).where(
            ProviderConnection.id == connection_id,
            ProviderConnection.project_id == project_id,
            ProviderConnection.connector == connector,
            ProviderConnection.status != "disconnected",
        )
    )
    if connection is None:
        raise NotFoundError("The requested provider connection was not found.")
    return connection


def list_connections_for_project(
    session: Session,
    *,
    project_id: str,
    connector: str = "supabase",
) -> list[ProviderConnection]:
    return list(
        session.scalars(
            select(ProviderConnection)
            .where(
                ProviderConnection.project_id == project_id,
                ProviderConnection.connector == connector,
                ProviderConnection.status != "disconnected",
            )
            .order_by(ProviderConnection.created_at.desc())
        )
    )
