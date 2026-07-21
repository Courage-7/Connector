"""Typed REST and MCP inputs for Supabase tools."""

from pydantic import Field

from connector_service.core.contracts import StrictModel
from connector_service.providers.supabase.connection_schemas import TableQuery


class ConnectionToolInput(StrictModel):
    connection_id: str = Field(min_length=36, max_length=36)


class SelectProjectInput(ConnectionToolInput):
    project_ref: str = Field(pattern=r"^[a-z0-9]{20}$")


class DescribeTableInput(ConnectionToolInput):
    schema_name: str = Field(min_length=1, max_length=63)
    table_name: str = Field(min_length=1, max_length=63)


class QueryTableInput(ConnectionToolInput):
    query: TableQuery
