"""OAuth and owner-scoped provider connection endpoints."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Query, Request, status

from connector_service.bootstrap.dependencies import (
    AuthenticatedPrincipal,
    RepositoryDependency,
)
from connector_service.connections.schemas import (
    AuthorizationStartResponse,
    ConnectionResponse,
    OAuthCallbackResponse,
    SupabaseAuthorizationRequest,
)
from connector_service.connections.service import ConnectionService
from connector_service.core.exceptions import InvalidRequestError

router = APIRouter(tags=["Connections"])


def _service(request: Request) -> ConnectionService:
    return request.app.state.connection_service


@router.post(
    "/v1/connections/supabase/authorize",
    response_model=AuthorizationStartResponse,
)
async def authorize_supabase(
    body: SupabaseAuthorizationRequest,
    request: Request,
    principal: AuthenticatedPrincipal,
    repository: RepositoryDependency,
) -> AuthorizationStartResponse:
    return await _service(request).start_supabase_authorization(
        principal=principal,
        repository=repository,
        organization_slug=body.organization_slug,
    )


@router.get(
    "/v1/oauth/supabase/callback",
    response_model=OAuthCallbackResponse,
)
async def supabase_callback(
    request: Request,
    repository: RepositoryDependency,
    code: Annotated[str | None, Query(min_length=1, max_length=2048)] = None,
    state_value: Annotated[
        str | None,
        Query(alias="state", min_length=1, max_length=512),
    ] = None,
    provider_error: Annotated[
        str | None,
        Query(alias="error", max_length=200),
    ] = None,
) -> OAuthCallbackResponse:
    return await _service(request).complete_supabase_authorization(
        repository=repository,
        code=code,
        state=state_value,
        provider_error=provider_error,
    )


@router.get("/v1/connections", response_model=list[ConnectionResponse])
async def list_connections(
    principal: AuthenticatedPrincipal,
    repository: RepositoryDependency,
    provider: Annotated[str | None, Query(max_length=40)] = None,
) -> list[ConnectionResponse]:
    connections = await repository.list_connections(owner_subject=principal.subject)
    if provider is not None:
        connections = [item for item in connections if item.provider == provider]
    return [ConnectionService.response(item) for item in connections]


@router.get("/v1/connections/{connection_id}", response_model=ConnectionResponse)
async def get_connection(
    connection_id: str,
    principal: AuthenticatedPrincipal,
    repository: RepositoryDependency,
) -> ConnectionResponse:
    connection = await repository.get_connection(
        connection_id=connection_id,
        owner_subject=principal.subject,
    )
    return ConnectionService.response(connection)


@router.delete(
    "/v1/connections/{connection_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def disconnect_connection(
    connection_id: str,
    request: Request,
    principal: AuthenticatedPrincipal,
    repository: RepositoryDependency,
) -> None:
    connection = await repository.get_connection(
        connection_id=connection_id,
        owner_subject=principal.subject,
    )
    if connection.provider != "supabase":
        raise InvalidRequestError("This provider is not implemented in the current phase.")
    await _service(request).disconnect_supabase(
        connection=connection,
        repository=repository,
    )
