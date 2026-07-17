"""Approval-gated agent queries and dashboard governance routes."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request
from pydantic import Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from connector_service.api.connections import _active_connection, _project_ref
from connector_service.api.dependencies import (
    get_session,
    require_dashboard_project,
    require_project,
)
from connector_service.connectors.supabase.catalog import SupabaseCatalog
from connector_service.connectors.supabase.connection_schemas import (
    TableQuery,
    TableQueryResponse,
    validate_catalog_identifier,
)
from connector_service.core.contracts import StrictModel
from connector_service.core.exceptions import (
    AuthorizationError,
    ConflictError,
    NotFoundError,
    ServiceError,
)
from connector_service.db.models import (
    AgentAccessPolicy,
    AgentQueryRequest,
    Project,
    QueryAuditRecord,
)
from connector_service.db.repositories import get_connection_for_project
from connector_service.query_governance import (
    complete_query_audit,
    fail_query_audit,
    start_query_audit,
)

agent_router = APIRouter(prefix="/v1/agent", tags=["agent tools"])
dashboard_router = APIRouter(prefix="/v1/dashboard", tags=["dashboard governance"])


class AgentPolicyUpdate(StrictModel):
    approval_mode: Literal["always", "never"] = "always"
    max_rows: int = Field(default=25, ge=1, le=100)
    allowed_schemas: list[str] = Field(default_factory=lambda: ["public"], min_length=1)
    masked_columns: dict[str, list[str]] = Field(default_factory=dict)

    @field_validator("allowed_schemas")
    @classmethod
    def validate_schemas(cls, values: list[str]) -> list[str]:
        normalized = [validate_catalog_identifier(value) for value in values]
        if len(normalized) != len(set(normalized)):
            raise ValueError("allowed_schemas must not contain duplicates")
        return normalized

    @field_validator("masked_columns")
    @classmethod
    def validate_masks(cls, value: dict[str, list[str]]) -> dict[str, list[str]]:
        if len(value) > 100:
            raise ValueError("too many masked relations")
        for relation, columns in value.items():
            try:
                schema_name, table_name = relation.split(".", maxsplit=1)
            except ValueError as exc:
                raise ValueError("masked relation keys must be schema.table") from exc
            validate_catalog_identifier(schema_name)
            validate_catalog_identifier(table_name)
            normalized = [validate_catalog_identifier(column) for column in columns]
            if len(normalized) != len(set(normalized)):
                raise ValueError("masked columns must not contain duplicates")
        return value


class AgentPolicyResponse(AgentPolicyUpdate):
    connection_id: str


class AgentQueryRequestResponse(StrictModel):
    id: str
    connection_id: str
    status: str
    query: TableQuery
    requested_at: datetime
    decided_at: datetime | None
    decision_note: str | None


class QueryDecision(StrictModel):
    note: str | None = Field(default=None, max_length=500)


class QueryAuditResponse(StrictModel):
    id: str
    connection_id: str
    query_request_id: str | None
    actor_type: str
    schema_name: str
    table_name: str
    columns: list[str]
    filters: list[dict[str, object]]
    order_by: list[dict[str, object]]
    row_limit: int
    status: str
    returned_rows: int | None
    error_code: str | None
    created_at: datetime
    completed_at: datetime | None


@agent_router.post(
    "/connections/{connection_id}/query-requests",
    response_model=AgentQueryRequestResponse,
)
async def request_agent_query(
    connection_id: str,
    body: TableQuery,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> AgentQueryRequestResponse:
    connection, access_token = await _active_connection(
        connection_id=connection_id,
        request=request,
        session=session,
        project=project,
    )
    policy = _get_or_create_policy(session, project.id, connection.id)
    if body.schema_name not in policy.allowed_schemas:
        raise AuthorizationError("The agent is not allowed to query this schema.")
    if body.limit > policy.max_rows:
        raise AuthorizationError(
            "The requested row limit exceeds the agent policy.",
            details={"max_rows": policy.max_rows},
        )

    catalog = SupabaseCatalog(request.app.state.supabase_management)
    description = await catalog.describe_table(
        access_token=access_token,
        project_ref=_project_ref(connection),
        schema_name=body.schema_name,
        table_name=body.table_name,
    )
    available = {column.name for column in description.columns}
    referenced = set(body.columns)
    referenced.update(item.column for item in body.filters)
    referenced.update(item.column for item in body.order)
    if not referenced.issubset(available):
        raise AuthorizationError("The query references a column that is not available.")
    relation_key = f"{body.schema_name}.{body.table_name}"
    masked = set(policy.masked_columns.get(relation_key, []))
    if referenced.intersection(masked):
        raise AuthorizationError("The query references a masked column.")

    query_request = AgentQueryRequest(
        project_id=project.id,
        connection_id=connection.id,
        query=body.model_dump(mode="json"),
        status="pending" if policy.approval_mode == "always" else "approved",
    )
    session.add(query_request)
    session.commit()
    return _query_request_response(query_request)


@agent_router.get(
    "/query-requests/{query_request_id}",
    response_model=AgentQueryRequestResponse,
)
def get_agent_query_request(
    query_request_id: str,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> AgentQueryRequestResponse:
    return _query_request_response(_get_query_request(session, query_request_id, project.id))


@agent_router.post(
    "/query-requests/{query_request_id}/execute",
    response_model=TableQueryResponse,
)
async def execute_agent_query(
    query_request_id: str,
    request: Request,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_project)],
) -> TableQueryResponse:
    query_request = _get_query_request(session, query_request_id, project.id)
    if query_request.status != "approved":
        raise ConflictError("The query request must be approved before execution.")
    connection, access_token = await _active_connection(
        connection_id=query_request.connection_id,
        request=request,
        session=session,
        project=project,
    )
    query = TableQuery.model_validate(query_request.query)
    audit = start_query_audit(
        session,
        request=request,
        project=project,
        connection=connection,
        query=query,
        actor_type="agent",
        query_request_id=query_request.id,
    )
    catalog = SupabaseCatalog(request.app.state.supabase_management)
    try:
        rows = await catalog.query_table(
            access_token=access_token,
            project_ref=_project_ref(connection),
            request=query,
        )
    except ServiceError as exc:
        fail_query_audit(session, audit, error_code=exc.code)
        raise
    except Exception:
        fail_query_audit(session, audit, error_code="internal_error")
        raise
    query_request.status = "executed"
    query_request.executed_at = datetime.now(UTC)
    session.commit()
    complete_query_audit(session, audit, returned_rows=len(rows))
    return TableQueryResponse(data=rows, returned=len(rows), limit=query.limit)


@dashboard_router.get(
    "/connections/{connection_id}/agent-policy",
    response_model=AgentPolicyResponse,
)
def get_agent_policy(
    connection_id: str,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_dashboard_project)],
) -> AgentPolicyResponse:
    connection = get_connection_for_project(
        session,
        connection_id=connection_id,
        project_id=project.id,
    )
    policy = _find_policy(session, project.id, connection.id)
    if policy is None:
        return AgentPolicyResponse(
            connection_id=connection.id,
            approval_mode="always",
            max_rows=25,
            allowed_schemas=["public"],
            masked_columns={},
        )
    return _policy_response(policy)


@dashboard_router.put(
    "/connections/{connection_id}/agent-policy",
    response_model=AgentPolicyResponse,
)
def update_agent_policy(
    connection_id: str,
    body: AgentPolicyUpdate,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_dashboard_project)],
) -> AgentPolicyResponse:
    connection = get_connection_for_project(
        session,
        connection_id=connection_id,
        project_id=project.id,
    )
    policy = _get_or_create_policy(session, project.id, connection.id)
    policy.approval_mode = body.approval_mode
    policy.max_rows = body.max_rows
    policy.allowed_schemas = body.allowed_schemas
    policy.masked_columns = body.masked_columns
    session.commit()
    return _policy_response(policy)


@dashboard_router.get("/query-requests", response_model=list[AgentQueryRequestResponse])
def list_query_requests(
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_dashboard_project)],
    request_status: Annotated[
        Literal["pending", "approved", "denied", "executed"] | None,
        Query(alias="status"),
    ] = None,
) -> list[AgentQueryRequestResponse]:
    statement = select(AgentQueryRequest).where(AgentQueryRequest.project_id == project.id)
    if request_status:
        statement = statement.where(AgentQueryRequest.status == request_status)
    rows = session.scalars(statement.order_by(AgentQueryRequest.requested_at.desc()).limit(100))
    return [_query_request_response(row) for row in rows]


@dashboard_router.post(
    "/query-requests/{query_request_id}/approve",
    response_model=AgentQueryRequestResponse,
)
def approve_query_request(
    query_request_id: str,
    body: QueryDecision,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_dashboard_project)],
) -> AgentQueryRequestResponse:
    row = _get_query_request(session, query_request_id, project.id)
    if row.status != "pending":
        raise ConflictError("Only pending query requests can be approved.")
    row.status = "approved"
    row.decision_note = body.note
    row.decided_at = datetime.now(UTC)
    session.commit()
    return _query_request_response(row)


@dashboard_router.post(
    "/query-requests/{query_request_id}/deny",
    response_model=AgentQueryRequestResponse,
)
def deny_query_request(
    query_request_id: str,
    body: QueryDecision,
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_dashboard_project)],
) -> AgentQueryRequestResponse:
    row = _get_query_request(session, query_request_id, project.id)
    if row.status != "pending":
        raise ConflictError("Only pending query requests can be denied.")
    row.status = "denied"
    row.decision_note = body.note
    row.decided_at = datetime.now(UTC)
    session.commit()
    return _query_request_response(row)


@dashboard_router.get("/audit", response_model=list[QueryAuditResponse])
def list_query_audit(
    session: Annotated[Session, Depends(get_session)],
    project: Annotated[Project, Depends(require_dashboard_project)],
    limit: Annotated[int, Query(ge=1, le=200)] = 100,
) -> list[QueryAuditResponse]:
    rows = session.scalars(
        select(QueryAuditRecord)
        .where(QueryAuditRecord.project_id == project.id)
        .order_by(QueryAuditRecord.created_at.desc())
        .limit(limit)
    )
    return [QueryAuditResponse.model_validate(row, from_attributes=True) for row in rows]


def _get_or_create_policy(
    session: Session,
    project_id: str,
    connection_id: str,
) -> AgentAccessPolicy:
    policy = _find_policy(session, project_id, connection_id)
    if policy is None:
        policy = AgentAccessPolicy(
            project_id=project_id,
            connection_id=connection_id,
            approval_mode="always",
            max_rows=25,
            allowed_schemas=["public"],
            masked_columns={},
        )
        session.add(policy)
        session.commit()
    return policy


def _find_policy(
    session: Session,
    project_id: str,
    connection_id: str,
) -> AgentAccessPolicy | None:
    return session.scalar(
        select(AgentAccessPolicy).where(
            AgentAccessPolicy.project_id == project_id,
            AgentAccessPolicy.connection_id == connection_id,
        )
    )


def _get_query_request(
    session: Session,
    query_request_id: str,
    project_id: str,
) -> AgentQueryRequest:
    row = session.scalar(
        select(AgentQueryRequest).where(
            AgentQueryRequest.id == query_request_id,
            AgentQueryRequest.project_id == project_id,
        )
    )
    if row is None:
        raise NotFoundError("The query request was not found.")
    return row


def _policy_response(policy: AgentAccessPolicy) -> AgentPolicyResponse:
    return AgentPolicyResponse(
        connection_id=policy.connection_id,
        approval_mode=policy.approval_mode,
        max_rows=policy.max_rows,
        allowed_schemas=policy.allowed_schemas,
        masked_columns=policy.masked_columns,
    )


def _query_request_response(row: AgentQueryRequest) -> AgentQueryRequestResponse:
    return AgentQueryRequestResponse(
        id=row.id,
        connection_id=row.connection_id,
        status=row.status,
        query=TableQuery.model_validate(row.query),
        requested_at=row.requested_at,
        decided_at=row.decided_at,
        decision_note=row.decision_note,
    )
