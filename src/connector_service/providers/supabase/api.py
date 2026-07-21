"""Typed Supabase tool endpoints shared conceptually with MCP."""

from __future__ import annotations

from fastapi import APIRouter, Request

from connector_service.bootstrap.dependencies import (
    AuthenticatedPrincipal,
    RepositoryDependency,
)
from connector_service.connections.schemas import ConnectionResponse
from connector_service.providers.supabase.connection_schemas import (
    SupabaseProjectSummary,
    TableDescription,
    TableQueryResponse,
    TableSummary,
)
from connector_service.providers.supabase.tool_schemas import (
    ConnectionToolInput,
    DescribeTableInput,
    QueryTableInput,
    SelectProjectInput,
)
from connector_service.providers.supabase.tools import SupabaseToolService

router = APIRouter(prefix="/v1/tools/supabase", tags=["Supabase Tools"])


def _service(request: Request) -> SupabaseToolService:
    return request.app.state.supabase_tools


@router.post("/list-projects", response_model=list[SupabaseProjectSummary])
async def list_projects(
    body: ConnectionToolInput,
    request: Request,
    principal: AuthenticatedPrincipal,
    repository: RepositoryDependency,
) -> list[SupabaseProjectSummary]:
    return await _service(request).list_projects(
        principal=principal,
        repository=repository,
        connection_id=body.connection_id,
    )


@router.post("/select-project", response_model=ConnectionResponse)
async def select_project(
    body: SelectProjectInput,
    request: Request,
    principal: AuthenticatedPrincipal,
    repository: RepositoryDependency,
) -> ConnectionResponse:
    return await _service(request).select_project(
        principal=principal,
        repository=repository,
        connection_id=body.connection_id,
        project_ref=body.project_ref,
    )


@router.post("/list-tables", response_model=list[TableSummary])
async def list_tables(
    body: ConnectionToolInput,
    request: Request,
    principal: AuthenticatedPrincipal,
    repository: RepositoryDependency,
) -> list[TableSummary]:
    return await _service(request).list_tables(
        principal=principal,
        repository=repository,
        connection_id=body.connection_id,
    )


@router.post("/describe-table", response_model=TableDescription)
async def describe_table(
    body: DescribeTableInput,
    request: Request,
    principal: AuthenticatedPrincipal,
    repository: RepositoryDependency,
) -> TableDescription:
    return await _service(request).describe_table(
        principal=principal,
        repository=repository,
        connection_id=body.connection_id,
        schema_name=body.schema_name,
        table_name=body.table_name,
    )


@router.post("/query-table", response_model=TableQueryResponse)
async def query_table(
    body: QueryTableInput,
    request: Request,
    principal: AuthenticatedPrincipal,
    repository: RepositoryDependency,
) -> TableQueryResponse:
    return await _service(request).query_table(
        principal=principal,
        repository=repository,
        connection_id=body.connection_id,
        query=body.query,
    )
