"""Query audit helpers shared by browser, API, and agent execution paths."""

from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy.orm import Session

from connector_service.connectors.supabase.connection_schemas import TableQuery
from connector_service.db.models import Project, ProviderConnection, QueryAuditRecord


def start_query_audit(
    session: Session,
    *,
    request: Request,
    project: Project,
    connection: ProviderConnection,
    query: TableQuery,
    actor_type: str | None = None,
    query_request_id: str | None = None,
) -> QueryAuditRecord:
    record = QueryAuditRecord(
        project_id=project.id,
        connection_id=connection.id,
        query_request_id=query_request_id,
        actor_type=actor_type or getattr(request.state, "auth_mode", "api"),
        schema_name=query.schema_name,
        table_name=query.table_name,
        columns=query.columns,
        filters=[
            {"column": item.column, "value_present": item.value is not None}
            for item in query.filters
        ],
        order_by=[item.model_dump(mode="json") for item in query.order],
        row_limit=query.limit,
        status="running",
    )
    session.add(record)
    session.commit()
    return record


def complete_query_audit(
    session: Session,
    record: QueryAuditRecord,
    *,
    returned_rows: int,
) -> None:
    record.status = "succeeded"
    record.returned_rows = returned_rows
    record.completed_at = datetime.now(UTC)
    session.commit()


def fail_query_audit(
    session: Session,
    record: QueryAuditRecord,
    *,
    error_code: str,
) -> None:
    record.status = "failed"
    record.error_code = error_code
    record.completed_at = datetime.now(UTC)
    session.commit()
