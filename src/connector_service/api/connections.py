"""User-authorized Supabase connection and live data-discovery routes."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import RedirectResponse
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from connector_service.api.dependencies import get_session, require_project
from connector_service.config import Settings
from connector_service.connectors.oauth import create_oauth_material, digest_oauth_state
from connector_service.core.exceptions import (
    ConflictError,
    InvalidRequestError,
    NotFoundError,
    ServiceError,
)
from connector_service.core.security import CredentialCipher
from connector_service.db.models import OAuthAttempt, Project, ProviderConnection
from connector_service.db.repositories import (
    consume_oauth_attempt,
    get_connection_for_project,
    list_connections_for_project,
)
from connector_service.providers.catalog import ProviderCatalog
from connector_service.providers.supabase.catalog import SupabaseCatalog
from connector_service.providers.supabase.connection_schemas import (
    ProviderConnectionResponse,
    SupabaseOAuthCallbackResponse,
    SupabaseOAuthStart,
    SupabaseOAuthStartResponse,
    SupabaseProjectSelection,
    SupabaseProjectSummary,
    TableDescription,
    TableQuery,
    TableQueryResponse,
    TableSummary,
    validate_catalog_identifier,
)
from connector_service.providers.supabase.management import (
    OAuthTokens,
    SupabaseManagementClient,
)
from connector_service.query_governance import (
    complete_query_audit,
    fail_query_audit,
    start_query_audit,
)

router = APIRouter(prefix="/v1/connections/supabase", tags=["Supabase connections"])


@router.post("/authorize", response_model=SupabaseOAuthStartResponse)
def start_authorization(
    body: SupabaseOAuthStart,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> SupabaseOAuthStartResponse:
    settings: Settings = request.app.state.settings
    client = _management_client(request)
    cipher: CredentialCipher = request.app.state.credential_cipher
    material = create_oauth_material()
    expires_at = datetime.now(UTC) + timedelta(seconds=settings.supabase_oauth_attempt_ttl_seconds)
    authorization_url = client.authorization_url(
        state=material.state,
        code_challenge=material.code_challenge,
        organization_slug=body.organization_slug,
    )
    encrypted_context = {"code_verifier": material.code_verifier}
    if body.return_to is not None:
        if getattr(request.state, "auth_mode", None) != "dashboard":
            raise InvalidRequestError("A dashboard session is required for return navigation.")
        encrypted_context["return_to"] = body.return_to
    session.add(
        OAuthAttempt(
            project_id=project.id,
            connector="supabase",
            state_digest=material.state_digest,
            encrypted_context=cipher.encrypt(encrypted_context),
            expires_at=expires_at,
        )
    )
    session.commit()
    return SupabaseOAuthStartResponse(
        authorization_url=authorization_url,
        expires_at=expires_at,
    )


@router.get("/callback", response_model=SupabaseOAuthCallbackResponse)
async def complete_authorization(
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    code: Annotated[str | None, Query(min_length=1, max_length=2048)] = None,
    state_value: Annotated[
        str | None,
        Query(alias="state", min_length=1, max_length=512),
    ] = None,
    provider_error: Annotated[str | None, Query(alias="error", max_length=200)] = None,
) -> SupabaseOAuthCallbackResponse | RedirectResponse:
    if provider_error or not code or not state_value:
        raise InvalidRequestError("Supabase authorization was not completed.")
    attempt = consume_oauth_attempt(
        session,
        state_digest=digest_oauth_state(state_value),
        connector="supabase",
    )
    cipher: CredentialCipher = request.app.state.credential_cipher
    context = cipher.decrypt(attempt.encrypted_context)
    code_verifier = context.get("code_verifier")
    if not isinstance(code_verifier, str) or not code_verifier:
        raise InvalidRequestError("The stored OAuth attempt is invalid.")
    client = _management_client(request)
    tokens = await client.exchange_code(code=code, code_verifier=code_verifier)
    connection = ProviderConnection(
        project_id=attempt.project_id,
        connector="supabase",
        status="pending_project",
        encrypted_secret=cipher.encrypt(tokens.secret_document()),
        token_expires_at=tokens.expires_at,
    )
    session.add(connection)
    session.commit()
    return_to = context.get("return_to")
    if isinstance(return_to, str) and return_to.startswith("/app"):
        query = urlencode({"connection_id": connection.id, "status": connection.status})
        return RedirectResponse(f"{return_to}?{query}", status_code=status.HTTP_303_SEE_OTHER)
    return SupabaseOAuthCallbackResponse(connection=_connection_response(connection))


@router.get("", response_model=list[ProviderConnectionResponse])
def list_connections(
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> list[ProviderConnectionResponse]:
    return [
        _connection_response(connection)
        for connection in list_connections_for_project(session, project_id=project.id)
    ]


@router.get("/{connection_id}/projects", response_model=list[SupabaseProjectSummary])
async def list_available_projects(
    connection_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> list[SupabaseProjectSummary]:
    connection = get_connection_for_project(
        session,
        connection_id=connection_id,
        project_id=project.id,
    )
    access_token = await _valid_access_token(connection, request, session)
    client = _management_client(request)
    provider_projects = await client.list_projects(access_token)
    return [_project_summary(item) for item in provider_projects]


@router.post(
    "/{connection_id}/select-project",
    response_model=ProviderConnectionResponse,
)
async def select_project(
    connection_id: str,
    body: SupabaseProjectSelection,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> ProviderConnectionResponse:
    connection = get_connection_for_project(
        session,
        connection_id=connection_id,
        project_id=project.id,
    )
    access_token = await _valid_access_token(connection, request, session)
    client = _management_client(request)
    provider_projects = await client.list_projects(access_token)
    selected = next(
        (item for item in provider_projects if item.get("ref") == body.project_ref),
        None,
    )
    if selected is None:
        raise NotFoundError("The selected Supabase project is not available to this authorization.")
    summary = _project_summary(selected)
    connection.external_ref = summary.ref
    connection.name = summary.name
    connection.status = "active"
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError("This Supabase project is already connected.") from exc
    return _connection_response(connection)


@router.get("/{connection_id}/tables", response_model=list[TableSummary])
async def list_tables(
    connection_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> list[TableSummary]:
    connection, access_token = await _active_connection(
        connection_id=connection_id,
        request=request,
        session=session,
        project=project,
    )
    catalog = SupabaseCatalog(_management_client(request))
    return await catalog.list_tables(
        access_token=access_token,
        project_ref=_project_ref(connection),
    )


@router.get(
    "/{connection_id}/tables/{schema_name}/{table_name}",
    response_model=TableDescription,
)
async def describe_table(
    connection_id: str,
    schema_name: str,
    table_name: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> TableDescription:
    validated_schema = validate_catalog_identifier(schema_name)
    validated_table = validate_catalog_identifier(table_name)
    connection, access_token = await _active_connection(
        connection_id=connection_id,
        request=request,
        session=session,
        project=project,
    )
    catalog = SupabaseCatalog(_management_client(request))
    return await catalog.describe_table(
        access_token=access_token,
        project_ref=_project_ref(connection),
        schema_name=validated_schema,
        table_name=validated_table,
    )


@router.post("/{connection_id}/query", response_model=TableQueryResponse)
async def query_table(
    connection_id: str,
    body: TableQuery,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> TableQueryResponse:
    connection, access_token = await _active_connection(
        connection_id=connection_id,
        request=request,
        session=session,
        project=project,
    )
    catalog = SupabaseCatalog(_management_client(request))
    audit = start_query_audit(
        session,
        request=request,
        project=project,
        connection=connection,
        query=body,
    )
    try:
        rows = await catalog.query_table(
            access_token=access_token,
            project_ref=_project_ref(connection),
            request=body,
        )
    except ServiceError as exc:
        fail_query_audit(session, audit, error_code=exc.code)
        raise
    except Exception:
        fail_query_audit(session, audit, error_code="internal_error")
        raise
    complete_query_audit(session, audit, returned_rows=len(rows))
    return TableQueryResponse(data=rows, returned=len(rows), limit=body.limit)


@router.delete("/{connection_id}", status_code=status.HTTP_204_NO_CONTENT)
async def disconnect(
    connection_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> None:
    connection = get_connection_for_project(
        session,
        connection_id=connection_id,
        project_id=project.id,
    )
    cipher: CredentialCipher = request.app.state.credential_cipher
    tokens = OAuthTokens.from_secret(cipher.decrypt(connection.encrypted_secret))
    client = _management_client(request)
    await client.revoke(tokens.refresh_token)
    connection.status = "disconnected"
    connection.encrypted_secret = cipher.encrypt({"revoked": True})
    session.commit()


async def _active_connection(
    *,
    connection_id: str,
    request: Request,
    session: Session,
    project: Project,
) -> tuple[ProviderConnection, str]:
    connection = get_connection_for_project(
        session,
        connection_id=connection_id,
        project_id=project.id,
    )
    if connection.status != "active" or connection.external_ref is None:
        raise InvalidRequestError("Select a Supabase project before querying this connection.")
    return connection, await _valid_access_token(connection, request, session)


async def _valid_access_token(
    connection: ProviderConnection,
    request: Request,
    session: Session,
) -> str:
    settings: Settings = request.app.state.settings
    cipher: CredentialCipher = request.app.state.credential_cipher
    tokens = OAuthTokens.from_secret(cipher.decrypt(connection.encrypted_secret))
    refresh_at = datetime.now(UTC) + timedelta(seconds=settings.supabase_oauth_token_skew_seconds)
    if tokens.expires_at <= refresh_at:
        client = _management_client(request)
        tokens = await client.refresh_tokens(tokens.refresh_token)
        connection.encrypted_secret = cipher.encrypt(tokens.secret_document())
        connection.token_expires_at = tokens.expires_at
        session.commit()
    return tokens.access_token


def _connection_response(connection: ProviderConnection) -> ProviderConnectionResponse:
    return ProviderConnectionResponse(
        id=connection.id,
        connector=connection.connector,
        status=connection.status,
        external_ref=connection.external_ref,
        name=connection.name,
        created_at=connection.created_at,
    )


def _project_summary(value: dict[str, Any]) -> SupabaseProjectSummary:
    try:
        return SupabaseProjectSummary.model_validate(
            {
                "ref": value.get("ref"),
                "name": value.get("name"),
                "organization_slug": value.get("organization_slug"),
                "region": value.get("region"),
                "status": value.get("status"),
            }
        )
    except ValidationError as exc:
        raise InvalidRequestError("Supabase returned invalid project metadata.") from exc


def _project_ref(connection: ProviderConnection) -> str:
    if connection.external_ref is None:
        raise InvalidRequestError("Select a Supabase project before querying this connection.")
    return connection.external_ref


def _management_client(request: Request) -> SupabaseManagementClient:
    providers: ProviderCatalog = request.app.state.providers
    return providers.require_service("supabase", SupabaseManagementClient)
