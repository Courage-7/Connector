from __future__ import annotations

import asyncio
import os

import pytest
from cryptography.fernet import Fernet
from dotenv import load_dotenv

from connector_service.config import Settings
from connector_service.connectors.supabase.catalog import SupabaseCatalog
from connector_service.connectors.supabase.connection_schemas import TableQuery
from connector_service.connectors.supabase.management import SupabaseManagementClient


def _required(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required live-test variable: {name}")
    return value


@pytest.mark.live
def test_real_management_api_discovery_and_table_query() -> None:
    load_dotenv(".env", override=False)
    load_dotenv(".env.live", override=False)
    access_token = _required("SUPABASE_MANAGEMENT_ACCESS_TOKEN")
    project_ref = _required("SUPABASE_PROJECT_REF")
    schema_name = os.getenv("SUPABASE_LIVE_SCHEMA", "public").strip()
    table_name = _required("SUPABASE_LIVE_TABLE")
    columns = [
        value.strip() for value in _required("SUPABASE_LIVE_COLUMNS").split(",") if value.strip()
    ]
    settings = Settings(
        environment="test",
        database_url="sqlite://",
        admin_token="live-admin-token-with-more-than-thirty-two-characters",
        credential_encryption_key=Fernet.generate_key().decode(),
        cursor_signing_key="live-cursor-key-with-more-than-thirty-two-characters",
        auto_create_schema=False,
        log_level="ERROR",
    )
    asyncio.run(
        _run_live_acceptance(
            settings=settings,
            access_token=access_token,
            project_ref=project_ref,
            schema_name=schema_name,
            table_name=table_name,
            columns=columns,
        )
    )


async def _run_live_acceptance(
    *,
    settings: Settings,
    access_token: str,
    project_ref: str,
    schema_name: str,
    table_name: str,
    columns: list[str],
) -> None:
    client = SupabaseManagementClient(settings)
    projects = await client.list_projects(access_token)
    assert any(project.get("ref") == project_ref for project in projects)

    catalog = SupabaseCatalog(client)
    tables = await catalog.list_tables(access_token=access_token, project_ref=project_ref)
    assert any(
        table.schema_name == schema_name and table.table_name == table_name for table in tables
    )
    description = await catalog.describe_table(
        access_token=access_token,
        project_ref=project_ref,
        schema_name=schema_name,
        table_name=table_name,
    )
    available_columns = {column.name for column in description.columns}
    assert set(columns).issubset(available_columns)

    rows = await catalog.query_table(
        access_token=access_token,
        project_ref=project_ref,
        request=TableQuery(
            schema_name=schema_name,
            table_name=table_name,
            columns=columns,
            limit=5,
        ),
    )
    assert len(rows) <= 5
