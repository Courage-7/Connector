"""OAuth and mailbox APIs for delegated Outlook and Gmail connections."""

from __future__ import annotations

from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from connector_service.api.dependencies import get_session, require_project
from connector_service.config import Settings
from connector_service.connectors.email.base import EmailClient
from connector_service.connectors.email.schemas import (
    AttachmentMetadata,
    DraftResponse,
    EmailCompose,
    EmailConnectionResponse,
    EmailOAuthCallbackResponse,
    EmailOAuthStart,
    EmailOAuthStartResponse,
    EmailProvider,
    MailFolder,
    MessageDetail,
    MessagePage,
    MessageSearch,
    MessageThread,
)
from connector_service.connectors.oauth import (
    OAuthTokenSet,
    create_oauth_material,
    digest_oauth_state,
)
from connector_service.core.exceptions import (
    ConflictError,
    InvalidRequestError,
    ProviderAccessError,
    ServiceError,
)
from connector_service.core.security import CredentialCipher
from connector_service.db.models import OAuthAttempt, Project, ProviderConnection
from connector_service.db.repositories import (
    consume_oauth_attempt,
    get_connection_for_project,
    list_connections_for_project,
)
from connector_service.email_governance import (
    complete_email_audit,
    fail_email_audit,
    start_email_audit,
)
from connector_service.providers.catalog import ProviderCatalog

router = APIRouter(prefix="/v1/connections", tags=["Email connections"])


@router.post("/{provider}/authorize", response_model=EmailOAuthStartResponse)
def start_email_authorization(
    provider: EmailProvider,
    body: EmailOAuthStart,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> EmailOAuthStartResponse:
    settings: Settings = request.app.state.settings
    client = _client(request, provider)
    cipher: CredentialCipher = request.app.state.credential_cipher
    material = create_oauth_material()
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.email_oauth_attempt_ttl_seconds)
    authorization_url = client.authorization_url(
        state=material.state,
        code_challenge=material.code_challenge,
        login_hint=body.login_hint,
    )
    context = {"code_verifier": material.code_verifier}
    if body.return_to is not None:
        if getattr(request.state, "auth_mode", None) != "dashboard":
            raise InvalidRequestError("A dashboard session is required for return navigation.")
        context["return_to"] = body.return_to
    session.add(
        OAuthAttempt(
            project_id=project.id,
            connector=provider.value,
            state_digest=material.state_digest,
            encrypted_context=cipher.encrypt(context),
            expires_at=expires_at,
        )
    )
    session.commit()
    return EmailOAuthStartResponse(authorization_url=authorization_url, expires_at=expires_at)


@router.get("/{provider}/callback", response_model=EmailOAuthCallbackResponse)
async def complete_email_authorization(
    provider: EmailProvider,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    code: Annotated[str | None, Query(min_length=1, max_length=4096)] = None,
    state_value: Annotated[str | None, Query(alias="state", min_length=1, max_length=512)] = None,
    provider_error: Annotated[str | None, Query(alias="error", max_length=200)] = None,
) -> EmailOAuthCallbackResponse | RedirectResponse:
    if provider_error or not code or not state_value:
        raise InvalidRequestError(f"{provider.value.title()} authorization was not completed.")
    attempt = consume_oauth_attempt(
        session,
        state_digest=digest_oauth_state(state_value),
        connector=provider.value,
    )
    cipher: CredentialCipher = request.app.state.credential_cipher
    context = cipher.decrypt(attempt.encrypted_context)
    code_verifier = context.get("code_verifier")
    if not isinstance(code_verifier, str) or not code_verifier:
        raise InvalidRequestError("The stored OAuth attempt is invalid.")
    client = _client(request, provider)
    tokens = await client.exchange_code(code=code, code_verifier=code_verifier)
    external_ref, name = await client.identity(tokens.access_token)
    connection = ProviderConnection(
        project_id=attempt.project_id,
        connector=provider.value,
        external_ref=external_ref,
        name=name,
        status="active",
        encrypted_secret=cipher.encrypt(tokens.secret_document()),
        token_expires_at=tokens.expires_at,
    )
    session.add(connection)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(f"This {provider.value.title()} mailbox is already connected.") from exc
    return_to = context.get("return_to")
    if isinstance(return_to, str) and return_to.startswith("/app"):
        query = urlencode({"connection_id": connection.id, "status": connection.status})
        return RedirectResponse(f"{return_to}?{query}", status_code=status.HTTP_303_SEE_OTHER)
    return EmailOAuthCallbackResponse(connection=_connection_response(connection))


@router.get("/{provider}", response_model=list[EmailConnectionResponse])
def list_email_connections(
    provider: EmailProvider,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> list[EmailConnectionResponse]:
    return [
        _connection_response(item)
        for item in list_connections_for_project(
            session,
            project_id=project.id,
            connector=provider.value,
        )
    ]


@router.get("/{provider}/{connection_id}/folders", response_model=list[MailFolder])
async def list_mail_folders(
    provider: EmailProvider,
    connection_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> list[MailFolder]:
    connection, token, client = await active_email_connection(
        provider, connection_id, request, session, project
    )
    audit = start_email_audit(
        session, request=request, project=project, connection=connection, action="list_folders"
    )
    try:
        folders = await client.list_folders(token)
    except ServiceError as exc:
        fail_email_audit(session, audit, error_code=exc.code)
        raise
    except Exception:
        fail_email_audit(session, audit, error_code="internal_error")
        raise
    complete_email_audit(session, audit, returned_items=len(folders))
    return folders


@router.post("/{provider}/{connection_id}/messages/search", response_model=MessagePage)
async def search_mail_messages(
    provider: EmailProvider,
    connection_id: str,
    body: MessageSearch,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> MessagePage:
    connection, token, client = await active_email_connection(
        provider, connection_id, request, session, project
    )
    audit = start_email_audit(
        session, request=request, project=project, connection=connection, action="search_messages"
    )
    try:
        result = await client.search_messages(token, body)
    except ServiceError as exc:
        fail_email_audit(session, audit, error_code=exc.code)
        raise
    except Exception:
        fail_email_audit(session, audit, error_code="internal_error")
        raise
    complete_email_audit(session, audit, returned_items=result.returned)
    return result


@router.get("/{provider}/{connection_id}/messages/{message_id}", response_model=MessageDetail)
async def get_mail_message(
    provider: EmailProvider,
    connection_id: str,
    message_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> MessageDetail:
    connection, token, client = await active_email_connection(
        provider, connection_id, request, session, project
    )
    audit = start_email_audit(
        session, request=request, project=project, connection=connection, action="get_message"
    )
    try:
        result = await client.get_message(token, message_id)
    except ServiceError as exc:
        fail_email_audit(session, audit, error_code=exc.code)
        raise
    except Exception:
        fail_email_audit(session, audit, error_code="internal_error")
        raise
    complete_email_audit(session, audit, returned_items=1)
    return result


@router.get(
    "/{provider}/{connection_id}/threads/{thread_id}",
    response_model=MessageThread,
)
async def get_mail_thread(
    provider: EmailProvider,
    connection_id: str,
    thread_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> MessageThread:
    connection, token, client = await active_email_connection(
        provider, connection_id, request, session, project
    )
    audit = start_email_audit(
        session, request=request, project=project, connection=connection, action="get_thread"
    )
    try:
        result = await client.get_thread(token, thread_id)
    except ServiceError as exc:
        fail_email_audit(session, audit, error_code=exc.code)
        raise
    except Exception:
        fail_email_audit(session, audit, error_code="internal_error")
        raise
    complete_email_audit(session, audit, returned_items=len(result.messages))
    return result


@router.get(
    "/{provider}/{connection_id}/messages/{message_id}/attachments",
    response_model=list[AttachmentMetadata],
)
async def list_mail_attachments(
    provider: EmailProvider,
    connection_id: str,
    message_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> list[AttachmentMetadata]:
    connection, token, client = await active_email_connection(
        provider, connection_id, request, session, project
    )
    audit = start_email_audit(
        session, request=request, project=project, connection=connection, action="list_attachments"
    )
    try:
        result = await client.list_attachments(token, message_id)
    except ServiceError as exc:
        fail_email_audit(session, audit, error_code=exc.code)
        raise
    except Exception:
        fail_email_audit(session, audit, error_code="internal_error")
        raise
    audit.attachment_count = len(result)
    complete_email_audit(session, audit, returned_items=len(result))
    return result


@router.post("/{provider}/{connection_id}/drafts", response_model=DraftResponse)
async def create_mail_draft(
    provider: EmailProvider,
    connection_id: str,
    body: EmailCompose,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> DraftResponse:
    connection, token, client = await active_email_connection(
        provider, connection_id, request, session, project
    )
    recipient_count = len(body.to + body.cc + body.bcc)
    audit = start_email_audit(
        session,
        request=request,
        project=project,
        connection=connection,
        action="create_draft",
        recipient_count=recipient_count,
    )
    try:
        result = await client.create_draft(token, body)
    except ServiceError as exc:
        fail_email_audit(session, audit, error_code=exc.code)
        raise
    except Exception:
        fail_email_audit(session, audit, error_code="internal_error")
        raise
    complete_email_audit(session, audit, returned_items=1)
    return result


@router.delete("/{provider}/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect_email(
    provider: EmailProvider,
    connection_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> None:
    connection = get_connection_for_project(
        session,
        connection_id=connection_id,
        project_id=project.id,
        connector=provider.value,
    )
    cipher: CredentialCipher = request.app.state.credential_cipher
    tokens = OAuthTokenSet.from_secret(cipher.decrypt(connection.encrypted_secret))
    # Disconnect must always remove the local credential. Remote revocation is
    # best-effort because a token may already be invalid or the provider may be down.
    with suppress(ServiceError):
        await _client(request, provider).revoke(tokens.refresh_token)
    connection.status = "disconnected"
    connection.encrypted_secret = cipher.encrypt({"revoked": True})
    session.commit()


async def active_email_connection(
    provider: EmailProvider,
    connection_id: str,
    request: Request,
    session: Session,
    project: Project,
) -> tuple[ProviderConnection, str, EmailClient]:
    connection = get_connection_for_project(
        session,
        connection_id=connection_id,
        project_id=project.id,
        connector=provider.value,
    )
    if connection.status != "active":
        raise InvalidRequestError("The mailbox connection is not active.")
    client = _client(request, provider)
    settings: Settings = request.app.state.settings
    cipher: CredentialCipher = request.app.state.credential_cipher
    tokens = OAuthTokenSet.from_secret(cipher.decrypt(connection.encrypted_secret))
    refresh_at = datetime.now(UTC) + timedelta(seconds=settings.email_oauth_token_skew_seconds)
    if tokens.expires_at <= refresh_at:
        locked = session.scalar(
            select(ProviderConnection)
            .where(
                ProviderConnection.id == connection.id,
                ProviderConnection.project_id == project.id,
                ProviderConnection.connector == provider.value,
            )
            .with_for_update()
        )
        if locked is None:
            raise InvalidRequestError("The mailbox connection is unavailable.")
        tokens = OAuthTokenSet.from_secret(cipher.decrypt(locked.encrypted_secret))
        if tokens.expires_at <= refresh_at:
            try:
                tokens = await client.refresh_tokens(tokens.refresh_token)
            except ProviderAccessError:
                locked.status = "reauthorization_required"
                session.commit()
                raise
            locked.encrypted_secret = cipher.encrypt(tokens.secret_document())
            locked.token_expires_at = tokens.expires_at
        session.commit()
    return connection, tokens.access_token, client


def _client(request: Request, provider: EmailProvider) -> EmailClient:
    providers: ProviderCatalog = request.app.state.providers
    return providers.email_client(provider.value)


def _connection_response(connection: ProviderConnection) -> EmailConnectionResponse:
    return EmailConnectionResponse(
        id=connection.id,
        connector=connection.connector,
        status=connection.status,
        external_ref=connection.external_ref,
        name=connection.name,
        created_at=connection.created_at,
    )
