"""Complete Supabase OAuth and REST tool flow."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import httpx
from conftest import PROJECT_REF, SupabaseMock, connect_supabase
from fastapi.testclient import TestClient


def test_supabase_oauth_and_tool_flow(
    client: TestClient,
    auth_headers: dict[str, str],
    supabase_mock: SupabaseMock,
) -> None:
    connection_id = connect_supabase(client, auth_headers)

    connections = client.get("/v1/connections", headers=auth_headers)
    assert connections.status_code == 200
    assert connections.json()[0]["status"] == "pending_resource"

    projects = client.post(
        "/v1/tools/supabase/list-projects",
        headers=auth_headers,
        json={"connection_id": connection_id},
    )
    assert projects.status_code == 200
    assert projects.json()[0]["ref"] == PROJECT_REF

    selected = client.post(
        "/v1/tools/supabase/select-project",
        headers=auth_headers,
        json={"connection_id": connection_id, "project_ref": PROJECT_REF},
    )
    assert selected.status_code == 200
    assert selected.json()["status"] == "active"
    assert selected.json()["display_name"] == "Cooking Project"

    tables = client.post(
        "/v1/tools/supabase/list-tables",
        headers=auth_headers,
        json={"connection_id": connection_id},
    )
    assert tables.status_code == 200
    assert tables.json() == [{"schema_name": "public", "table_name": "customers", "kind": "table"}]

    description = client.post(
        "/v1/tools/supabase/describe-table",
        headers=auth_headers,
        json={
            "connection_id": connection_id,
            "schema_name": "public",
            "table_name": "customers",
        },
    )
    assert description.status_code == 200
    assert [column["name"] for column in description.json()["columns"]] == ["id", "email"]

    result = client.post(
        "/v1/tools/supabase/query-table",
        headers=auth_headers,
        json={
            "connection_id": connection_id,
            "query": {
                "schema_name": "public",
                "table_name": "customers",
                "columns": ["id", "email"],
                "filters": [{"column": "email", "value": "person@example.com"}],
                "order": [{"column": "email", "direction": "asc"}],
                "limit": 10,
            },
        },
    )
    assert result.status_code == 200
    assert result.json()["returned"] == 1
    assert result.json()["data"][0]["email"] == "person@example.com"

    provider_calls = [
        request for request in supabase_mock.requests if "/projects" in request.url.path
    ]
    assert provider_calls
    assert all(
        request.headers.get("authorization") == "Bearer provider-access-token"
        for request in provider_calls
    )


def test_oauth_state_is_single_use(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    start = client.post(
        "/v1/connections/supabase/authorize",
        headers=auth_headers,
        json={},
    )
    state = httpx.URL(start.json()["authorization_url"]).params["state"]
    params = {"code": "authorization-code", "state": state}
    assert client.get("/v1/oauth/supabase/callback", params=params).status_code == 200
    replay = client.get("/v1/oauth/supabase/callback", params=params)
    assert replay.status_code == 422
    assert replay.json()["error"]["code"] == "invalid_request"


def test_provider_tokens_are_encrypted_at_rest(
    client: TestClient,
    auth_headers: dict[str, str],
    database_path: Path,
) -> None:
    connect_supabase(client, auth_headers)
    connection = sqlite3.connect(str(database_path))
    try:
        stored = connection.execute(
            "SELECT encrypted_credentials FROM provider_connections"
        ).fetchone()[0]
    finally:
        connection.close()
    assert b"provider-access-token" not in stored
    assert b"provider-refresh-token" not in stored


def test_database_tools_require_selected_project(
    client: TestClient,
    auth_headers: dict[str, str],
) -> None:
    connection_id = connect_supabase(client, auth_headers)
    response = client.post(
        "/v1/tools/supabase/list-tables",
        headers=auth_headers,
        json={"connection_id": connection_id},
    )
    assert response.status_code == 422
    assert "Select a Supabase project" in response.json()["error"]["message"]


def test_disconnect_revokes_and_hides_connection(
    client: TestClient,
    auth_headers: dict[str, str],
    supabase_mock: SupabaseMock,
) -> None:
    connection_id = connect_supabase(client, auth_headers)
    disconnected = client.delete(f"/v1/connections/{connection_id}", headers=auth_headers)
    assert disconnected.status_code == 204
    assert client.get("/v1/connections", headers=auth_headers).json() == []
    assert any(request.url.path == "/v1/oauth/revoke" for request in supabase_mock.requests)
