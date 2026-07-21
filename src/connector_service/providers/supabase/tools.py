"""Application service implementing the Supabase tool catalog."""

from __future__ import annotations

from typing import Any

from connector_service.connections.repository import ConnectionRepository
from connector_service.connections.schemas import ConnectionResponse
from connector_service.connections.service import ConnectionService
from connector_service.core.exceptions import ConflictError, InvalidRequestError, NotFoundError
from connector_service.identity.principal import Principal
from connector_service.infrastructure.database.models import ProviderConnection
from connector_service.providers.supabase.catalog import SupabaseCatalog
from connector_service.providers.supabase.connection_schemas import (
    SupabaseProjectSummary,
    TableDescription,
    TableQuery,
    TableQueryResponse,
    TableSummary,
)
from connector_service.providers.supabase.management import SupabaseManagementClient


class SupabaseToolService:
    def __init__(
        self,
        *,
        connections: ConnectionService,
        management: SupabaseManagementClient,
    ) -> None:
        self._connections = connections
        self._management = management
        self._catalog = SupabaseCatalog(management)

    async def list_projects(
        self,
        *,
        principal: Principal,
        repository: ConnectionRepository,
        connection_id: str,
    ) -> list[SupabaseProjectSummary]:
        connection = await self._get_connection(
            principal=principal,
            repository=repository,
            connection_id=connection_id,
        )
        access_token = await self._connections.access_token(
            connection=connection,
            repository=repository,
        )
        projects = await self._management.list_projects(access_token)
        return [self._project_summary(item) for item in projects]

    async def select_project(
        self,
        *,
        principal: Principal,
        repository: ConnectionRepository,
        connection_id: str,
        project_ref: str,
    ) -> ConnectionResponse:
        connection = await self._get_connection(
            principal=principal,
            repository=repository,
            connection_id=connection_id,
        )
        projects = await self.list_projects(
            principal=principal,
            repository=repository,
            connection_id=connection_id,
        )
        selected = next((item for item in projects if item.ref == project_ref), None)
        if selected is None:
            raise NotFoundError(
                "The selected Supabase project is not available to this authorization."
            )
        existing = await repository.list_connections(owner_subject=principal.subject)
        if any(
            item.id != connection.id
            and item.provider == "supabase"
            and item.external_reference == project_ref
            for item in existing
        ):
            raise ConflictError("This Supabase project is already connected.")
        connection.external_reference = selected.ref
        connection.display_name = selected.name
        connection.provider_metadata = {
            "organization_slug": selected.organization_slug,
            "region": selected.region,
        }
        connection.status = "active"
        await repository.save(connection)
        return ConnectionService.response(connection)

    async def list_tables(
        self,
        *,
        principal: Principal,
        repository: ConnectionRepository,
        connection_id: str,
    ) -> list[TableSummary]:
        connection, access_token = await self._active_connection(
            principal=principal,
            repository=repository,
            connection_id=connection_id,
        )
        return await self._catalog.list_tables(
            access_token=access_token,
            project_ref=self._project_ref(connection),
        )

    async def describe_table(
        self,
        *,
        principal: Principal,
        repository: ConnectionRepository,
        connection_id: str,
        schema_name: str,
        table_name: str,
    ) -> TableDescription:
        connection, access_token = await self._active_connection(
            principal=principal,
            repository=repository,
            connection_id=connection_id,
        )
        return await self._catalog.describe_table(
            access_token=access_token,
            project_ref=self._project_ref(connection),
            schema_name=schema_name,
            table_name=table_name,
        )

    async def query_table(
        self,
        *,
        principal: Principal,
        repository: ConnectionRepository,
        connection_id: str,
        query: TableQuery,
    ) -> TableQueryResponse:
        connection, access_token = await self._active_connection(
            principal=principal,
            repository=repository,
            connection_id=connection_id,
        )
        rows = await self._catalog.query_table(
            access_token=access_token,
            project_ref=self._project_ref(connection),
            request=query,
        )
        return TableQueryResponse(data=rows, returned=len(rows), limit=query.limit)

    async def _active_connection(
        self,
        *,
        principal: Principal,
        repository: ConnectionRepository,
        connection_id: str,
    ) -> tuple[ProviderConnection, str]:
        connection = await self._get_connection(
            principal=principal,
            repository=repository,
            connection_id=connection_id,
        )
        if connection.status != "active" or connection.external_reference is None:
            raise InvalidRequestError("Select a Supabase project before using database tools.")
        access_token = await self._connections.access_token(
            connection=connection,
            repository=repository,
        )
        return connection, access_token

    @staticmethod
    async def _get_connection(
        *,
        principal: Principal,
        repository: ConnectionRepository,
        connection_id: str,
    ) -> ProviderConnection:
        return await repository.get_connection(
            connection_id=connection_id,
            owner_subject=principal.subject,
            provider="supabase",
        )

    @staticmethod
    def _project_ref(connection: ProviderConnection) -> str:
        if connection.external_reference is None:
            raise InvalidRequestError("No Supabase project is selected.")
        return connection.external_reference

    @staticmethod
    def _project_summary(value: dict[str, Any]) -> SupabaseProjectSummary:
        try:
            return SupabaseProjectSummary.model_validate(
                {
                    "ref": value.get("id") or value.get("ref"),
                    "name": value.get("name"),
                    "organization_slug": value.get("organization_slug"),
                    "region": value.get("region"),
                    "status": value.get("status"),
                }
            )
        except ValueError as exc:
            raise InvalidRequestError("Supabase returned invalid project metadata.") from exc
