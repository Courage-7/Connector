"""Persistent models for credentials, projects, grants, and provider connections."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from connector_service.db.base import Base


def new_id() -> str:
    return str(uuid.uuid4())


def utc_now() -> datetime:
    return datetime.now(UTC)


class Credential(Base):
    __tablename__ = "credentials"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    connector: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    encrypted_secret: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ProjectApiKey(Base):
    __tablename__ = "project_api_keys"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    prefix: Mapped[str] = mapped_column(String(12), nullable=False, unique=True, index=True)
    salt: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    digest: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ConnectorGrant(Base):
    __tablename__ = "connector_grants"
    __table_args__ = (
        UniqueConstraint(
            "project_id", "credential_id", "connector", name="uq_grant_project_credential"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    credential_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("credentials.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connector: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    actions: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    policy: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class OAuthAttempt(Base):
    __tablename__ = "oauth_attempts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connector: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    state_digest: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False, unique=True, index=True
    )
    encrypted_context: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class ProviderConnection(Base):
    __tablename__ = "provider_connections"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "connector",
            "external_ref",
            name="uq_connection_project_connector_external_ref",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connector: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    external_ref: Mapped[str | None] = mapped_column(String(80), nullable=True)
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending_project")
    encrypted_secret: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class DashboardLoginTicket(Base):
    __tablename__ = "dashboard_login_tickets"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_digest: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False, unique=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class DashboardSession(Base):
    __tablename__ = "dashboard_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    token_digest: Mapped[bytes] = mapped_column(
        LargeBinary, nullable=False, unique=True, index=True
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class AgentAccessPolicy(Base):
    __tablename__ = "agent_access_policies"
    __table_args__ = (
        UniqueConstraint("project_id", "connection_id", name="uq_agent_policy_project_connection"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("provider_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    approval_mode: Mapped[str] = mapped_column(String(24), nullable=False, default="always")
    max_rows: Mapped[int] = mapped_column(Integer, nullable=False, default=25)
    allowed_schemas: Mapped[list[str]] = mapped_column(
        JSON, nullable=False, default=lambda: ["public"]
    )
    masked_columns: Mapped[dict[str, list[str]]] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now
    )


class AgentQueryRequest(Base):
    __tablename__ = "agent_query_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("provider_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    query: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class QueryAuditRecord(Base):
    __tablename__ = "query_audit_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("provider_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    query_request_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("agent_query_requests.id", ondelete="SET NULL"), nullable=True
    )
    actor_type: Mapped[str] = mapped_column(String(24), nullable=False)
    schema_name: Mapped[str] = mapped_column(String(63), nullable=False)
    table_name: Mapped[str] = mapped_column(String(63), nullable=False)
    columns: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    filters: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    order_by: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    row_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    returned_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmailSendRequest(Base):
    __tablename__ = "email_send_requests"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("provider_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    encrypted_message: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    payload_digest: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="pending", index=True)
    decision_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    requested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, index=True
    )
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EmailAuditRecord(Base):
    __tablename__ = "email_audit_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    connection_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("provider_connections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    send_request_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("email_send_requests.id", ondelete="SET NULL"), nullable=True
    )
    provider: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    action: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    actor_type: Mapped[str] = mapped_column(String(24), nullable=False)
    recipient_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    attachment_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    payload_digest: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    provider_reference: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    returned_items: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now, index=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
