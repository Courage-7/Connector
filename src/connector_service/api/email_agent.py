"""One-time approval and execution flow for agent-originated email sends."""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from connector_service.api.dependencies import (
    get_session,
    require_dashboard_project,
    require_project,
)
from connector_service.api.email_connections import active_email_connection
from connector_service.config import Settings
from connector_service.connectors.email.schemas import (
    EmailAuditResponse,
    EmailCompose,
    EmailDecision,
    EmailProvider,
    EmailSendExecutionResponse,
    EmailSendRequestResponse,
    EmailSendStatusResponse,
)
from connector_service.core.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ProviderUnavailableError,
    ServiceError,
)
from connector_service.core.security import CredentialCipher
from connector_service.db.models import (
    EmailAuditRecord,
    EmailSendRequest,
    Project,
)
from connector_service.db.repositories import get_connection_for_project
from connector_service.email_governance import (
    complete_email_audit,
    fail_email_audit,
    start_email_audit,
)

agent_router = APIRouter(prefix="/v1/agent", tags=["agent email tools"])
dashboard_router = APIRouter(prefix="/v1/dashboard", tags=["dashboard email governance"])


@agent_router.post(
    "/connections/{provider}/{connection_id}/email-send-requests",
    response_model=EmailSendStatusResponse,
)
def request_email_send(
    provider: EmailProvider,
    connection_id: str,
    body: EmailCompose,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> EmailSendStatusResponse:
    connection = get_connection_for_project(
        session,
        connection_id=connection_id,
        project_id=project.id,
        connector=provider.value,
    )
    if connection.status != "active":
        raise ConflictError("The mailbox connection is not active.")
    if body.bcc:
        raise AuthorizationError("Bcc is not enabled for agent-originated sends.")
    settings: Settings = request.app.state.settings
    cipher: CredentialCipher = request.app.state.credential_cipher
    document = body.model_dump(mode="json")
    digest = _payload_digest(document)
    now = datetime.now(UTC)
    row = EmailSendRequest(
        project_id=project.id,
        connection_id=connection.id,
        provider=provider.value,
        encrypted_message=cipher.encrypt(document),
        payload_digest=digest,
        status="pending",
        requested_at=now,
        expires_at=now + timedelta(seconds=settings.email_send_approval_ttl_seconds),
    )
    session.add(row)
    session.commit()
    return _status_response(row)


@agent_router.get(
    "/email-send-requests/{send_request_id}",
    response_model=EmailSendStatusResponse,
)
def get_email_send_status(
    send_request_id: str,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> EmailSendStatusResponse:
    return _status_response(_get_send_request(session, send_request_id, project.id))


@agent_router.post(
    "/email-send-requests/{send_request_id}/execute",
    response_model=EmailSendExecutionResponse,
)
async def execute_approved_email_send(
    send_request_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> EmailSendExecutionResponse:
    row = _get_send_request(session, send_request_id, project.id)
    now = datetime.now(UTC)
    if _as_utc(row.expires_at) <= now:
        if row.status in {"pending", "approved"}:
            row.status = "expired"
            session.commit()
        raise ConflictError("The email send approval has expired.")
    if row.status != "approved":
        raise ConflictError("The email send request must be approved before execution.")
    cipher: CredentialCipher = request.app.state.credential_cipher
    document = cipher.decrypt(row.encrypted_message)
    if not hmac.compare_digest(row.payload_digest, _payload_digest(document)):
        row.status = "invalid"
        session.commit()
        raise ConflictError("The approved email payload no longer matches its request.")
    message = EmailCompose.model_validate(document)
    provider = EmailProvider(row.provider)
    connection, access_token, client = await active_email_connection(
        provider, row.connection_id, request, session, project
    )
    row.status = "executing"
    session.commit()
    audit = start_email_audit(
        session,
        request=request,
        project=project,
        connection=connection,
        action="send_message",
        recipient_count=len(message.to + message.cc + message.bcc),
        actor_type="agent",
        send_request_id=row.id,
        payload_digest=row.payload_digest,
    )
    try:
        await client.send_message(access_token, message)
    except ProviderUnavailableError:
        row.status = "unknown"
        session.commit()
        fail_email_audit(session, audit, error_code="provider_outcome_unknown")
        raise
    except ServiceError as exc:
        row.status = "failed"
        session.commit()
        fail_email_audit(session, audit, error_code=exc.code)
        raise
    except Exception:
        row.status = "unknown"
        session.commit()
        fail_email_audit(session, audit, error_code="internal_outcome_unknown")
        raise
    row.status = "executed"
    row.executed_at = datetime.now(UTC)
    session.commit()
    complete_email_audit(session, audit, returned_items=1)
    return EmailSendExecutionResponse(
        request_id=row.id,
        provider=provider,
        status=row.status,
    )


@dashboard_router.get(
    "/email-send-requests",
    response_model=list[EmailSendRequestResponse],
)
def list_email_send_requests(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_dashboard_project)],
    request_status: Annotated[
        Literal["pending", "approved", "denied", "executing", "executed", "unknown"] | None,
        Query(alias="status"),
    ] = None,
) -> list[EmailSendRequestResponse]:
    statement = select(EmailSendRequest).where(EmailSendRequest.project_id == project.id)
    if request_status:
        statement = statement.where(EmailSendRequest.status == request_status)
    rows = session.scalars(statement.order_by(EmailSendRequest.requested_at.desc()).limit(100))
    cipher: CredentialCipher = request.app.state.credential_cipher
    return [_request_response(row, cipher) for row in rows]


@dashboard_router.post(
    "/email-send-requests/{send_request_id}/approve",
    response_model=EmailSendRequestResponse,
)
def approve_email_send(
    send_request_id: str,
    body: EmailDecision,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_dashboard_project)],
) -> EmailSendRequestResponse:
    row = _get_send_request(session, send_request_id, project.id)
    if row.status != "pending":
        raise ConflictError("Only pending email sends can be approved.")
    if _as_utc(row.expires_at) <= datetime.now(UTC):
        row.status = "expired"
        session.commit()
        raise ConflictError("The email send request has expired.")
    row.status = "approved"
    row.decision_note = body.note
    row.decided_at = datetime.now(UTC)
    session.commit()
    return _request_response(row, request.app.state.credential_cipher)


@dashboard_router.post(
    "/email-send-requests/{send_request_id}/deny",
    response_model=EmailSendRequestResponse,
)
def deny_email_send(
    send_request_id: str,
    body: EmailDecision,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_dashboard_project)],
) -> EmailSendRequestResponse:
    row = _get_send_request(session, send_request_id, project.id)
    if row.status != "pending":
        raise ConflictError("Only pending email sends can be denied.")
    row.status = "denied"
    row.decision_note = body.note
    row.decided_at = datetime.now(UTC)
    session.commit()
    return _request_response(row, request.app.state.credential_cipher)


@dashboard_router.get("/email-audit", response_model=list[EmailAuditResponse])
def list_email_audit(
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_dashboard_project)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[EmailAuditResponse]:
    rows = session.scalars(
        select(EmailAuditRecord)
        .where(EmailAuditRecord.project_id == project.id)
        .order_by(EmailAuditRecord.created_at.desc())
        .limit(limit)
    )
    return [EmailAuditResponse.model_validate(row, from_attributes=True) for row in rows]


def _get_send_request(session: Session, request_id: str, project_id: str) -> EmailSendRequest:
    row = session.scalar(
        select(EmailSendRequest).where(
            EmailSendRequest.id == request_id,
            EmailSendRequest.project_id == project_id,
        )
    )
    if row is None:
        raise NotFoundError("The email send request was not found.")
    return row


def _status_response(row: EmailSendRequest) -> EmailSendStatusResponse:
    return EmailSendStatusResponse(
        id=row.id,
        connection_id=row.connection_id,
        provider=EmailProvider(row.provider),
        status=row.status,
        requested_at=row.requested_at,
        expires_at=row.expires_at,
        decided_at=row.decided_at,
        decision_note=row.decision_note,
    )


def _request_response(
    row: EmailSendRequest,
    cipher: CredentialCipher,
) -> EmailSendRequestResponse:
    return EmailSendRequestResponse(
        **_status_response(row).model_dump(),
        message=EmailCompose.model_validate(cipher.decrypt(row.encrypted_message)),
    )


def _payload_digest(document: dict[str, object]) -> bytes:
    canonical = json.dumps(
        document,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).digest()


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)
