"""Live Supabase schema discovery and structured read-only table queries."""

from __future__ import annotations

from typing import Any

from connector_service.core.exceptions import InvalidRequestError, ProviderRequestError
from connector_service.providers.supabase.connection_schemas import (
    ColumnSummary,
    TableDescription,
    TableKind,
    TableQuery,
    TableSummary,
)
from connector_service.providers.supabase.management import SupabaseManagementClient

TABLES_QUERY = """
SELECT
    tables.table_schema AS schema_name,
    tables.table_name AS table_name,
    tables.table_type AS table_type
FROM information_schema.tables AS tables
WHERE tables.table_schema NOT IN (
    'auth', 'extensions', 'graphql', 'graphql_public', 'information_schema',
    'pg_catalog', 'pg_toast', 'realtime', 'storage', 'supabase_functions', 'vault'
)
AND tables.table_type IN ('BASE TABLE', 'VIEW')
AND has_schema_privilege(current_user, tables.table_schema, 'USAGE')
AND has_table_privilege(
    current_user,
    format('%I.%I', tables.table_schema, tables.table_name),
    'SELECT'
)
ORDER BY tables.table_schema, tables.table_name
""".strip()

COLUMNS_QUERY = """
SELECT
    columns.column_name AS name,
    columns.data_type AS data_type,
    columns.is_nullable = 'YES' AS nullable,
    columns.ordinal_position AS ordinal_position
FROM information_schema.columns AS columns
WHERE columns.table_schema = $1
AND columns.table_name = $2
ORDER BY columns.ordinal_position
""".strip()


class SupabaseCatalog:
    def __init__(self, client: SupabaseManagementClient) -> None:
        self._client = client

    async def list_tables(
        self,
        *,
        access_token: str,
        project_ref: str,
    ) -> list[TableSummary]:
        rows = await self._client.run_read_only_query(
            access_token=access_token,
            project_ref=project_ref,
            query=TABLES_QUERY,
        )
        tables: list[TableSummary] = []
        for row in rows:
            schema_name = row.get("schema_name")
            table_name = row.get("table_name")
            table_type = row.get("table_type")
            if not all(isinstance(value, str) for value in (schema_name, table_name, table_type)):
                raise ProviderRequestError("Supabase returned invalid table metadata.")
            kind = TableKind.TABLE if table_type == "BASE TABLE" else TableKind.VIEW
            tables.append(
                TableSummary(
                    schema_name=schema_name,
                    table_name=table_name,
                    kind=kind,
                )
            )
        return tables

    async def describe_table(
        self,
        *,
        access_token: str,
        project_ref: str,
        schema_name: str,
        table_name: str,
    ) -> TableDescription:
        tables = await self.list_tables(access_token=access_token, project_ref=project_ref)
        if not any(
            item.schema_name == schema_name and item.table_name == table_name for item in tables
        ):
            raise InvalidRequestError("The table is not available to this read-only connection.")
        rows = await self._client.run_read_only_query(
            access_token=access_token,
            project_ref=project_ref,
            query=COLUMNS_QUERY,
            parameters=[schema_name, table_name],
        )
        try:
            columns = [ColumnSummary.model_validate(row) for row in rows]
        except ValueError as exc:
            raise ProviderRequestError("Supabase returned invalid column metadata.") from exc
        if not columns:
            raise ProviderRequestError("Supabase did not return column metadata for the table.")
        return TableDescription(
            schema_name=schema_name,
            table_name=table_name,
            columns=columns,
        )

    async def query_table(
        self,
        *,
        access_token: str,
        project_ref: str,
        request: TableQuery,
    ) -> list[dict[str, Any]]:
        description = await self.describe_table(
            access_token=access_token,
            project_ref=project_ref,
            schema_name=request.schema_name,
            table_name=request.table_name,
        )
        available_columns = {column.name for column in description.columns}
        referenced_columns = set(request.columns)
        referenced_columns.update(item.column for item in request.filters)
        referenced_columns.update(item.column for item in request.order)
        if not referenced_columns.issubset(available_columns):
            raise InvalidRequestError("The query references a column that is not available.")

        selected = ", ".join(_quote_identifier(column) for column in request.columns)
        relation = (
            f"{_quote_identifier(request.schema_name)}.{_quote_identifier(request.table_name)}"
        )
        parameters: list[Any] = []
        predicates: list[str] = []
        for item in request.filters:
            column = _quote_identifier(item.column)
            if item.value is None:
                predicates.append(f"{column} IS NULL")
            else:
                parameters.append(item.value)
                predicates.append(f"{column} = ${len(parameters)}")

        query_parts = [f"SELECT {selected} FROM {relation}"]
        if predicates:
            query_parts.append(f"WHERE {' AND '.join(predicates)}")
        if request.order:
            order = ", ".join(
                f"{_quote_identifier(item.column)} {item.direction.value.upper()}"
                for item in request.order
            )
            query_parts.append(f"ORDER BY {order}")
        query_parts.append(f"LIMIT {request.limit}")
        rows = await self._client.run_read_only_query(
            access_token=access_token,
            project_ref=project_ref,
            query="\n".join(query_parts),
            parameters=parameters,
        )
        if len(rows) > request.limit:
            raise ProviderRequestError("Supabase returned more rows than requested.")
        return rows


def _quote_identifier(value: str) -> str:
    escaped = value.replace('"', '""')
    return f'"{escaped}"'
