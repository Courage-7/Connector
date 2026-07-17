"""Redacted audit helpers for mailbox reads, drafts, and sends."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy.orm import Session

from connector_service.db.models import EmailAuditRecord, Project, ProviderConnection


def start_email_audit(
    session: Session,
    *,
    request: Request,
    project: Project,
    connection: ProviderConnection,
    action: str,
    recipient_count: int = 0,
    attachment_count: int = 0,
    actor_type: str | None = None,
    send_request_id: str | None = None,
    payload_digest: bytes | None = None,
) -> EmailAuditRecord:
    record = EmailAuditRecord(
        project_id=project.id,
        connection_id=connection.id,
        send_request_id=send_request_id,
        provider=connection.connector,
        action=action,
        actor_type=actor_type or getattr(request.state, "auth_mode", "api"),
        recipient_count=recipient_count,
        attachment_count=attachment_count,
        payload_digest=payload_digest,
        status="running",
    )
    session.add(record)
    session.commit()
    return record


def complete_email_audit(
    session: Session,
    record: EmailAuditRecord,
    *,
    returned_items: int | None = None,
) -> None:
    record.status = "succeeded"
    record.returned_items = returned_items
    record.completed_at = datetime.now(UTC)
    session.commit()


def fail_email_audit(session: Session, record: EmailAuditRecord, *, error_code: str) -> None:
    record.status = "failed"
    record.error_code = error_code
    record.completed_at = datetime.now(UTC)
    session.commit()
