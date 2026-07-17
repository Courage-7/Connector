from __future__ import annotations

import json
from urllib.parse import parse_qs, urlparse

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import select

from connector_service.app import create_app
from connector_service.connectors.supabase.catalog import _quote_identifier
from connector_service.db.models import OAuthAttempt, ProviderConnection

PROJECT_REF = "abcdefghijklmnopqrst"


def test_complete_oauth_discovery_query_and_disconnect_flow(settings, admin_headers) -> None:
    observed_queries: list[dict[str, object]] = []

    def provider(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/v1/oauth/token":
            assert request.headers["authorization"].startswith("Basic ")
            form = parse_qs(request.content.decode())
            if form["grant_type"] == ["refresh_token"]:
                assert form["refresh_token"] == ["oauth-refresh-token"]
                return httpx.Response(
                    200,
                    json={
                        "access_token": "refreshed-access-token",
                        "refresh_token": "rotated-refresh-token",
                        "token_type": "Bearer",
                        "expires_in": 3600,
                    },
                )
            assert form["grant_type"] == ["authorization_code"]
            assert form["code"] == ["provider-code"]
            assert form["code_verifier"][0]
            return httpx.Response(
                200,
                json={
                    "access_token": "oauth-access-token",
                    "refresh_token": "oauth-refresh-token",
                    "token_type": "Bearer",
                    "expires_in": 1,
                },
            )
        if request.url.path == "/v1/projects" and request.method == "GET":
            assert request.headers["authorization"] == "Bearer refreshed-access-token"
            return httpx.Response(
                200,
                json=[
                    {
                        "ref": PROJECT_REF,
                        "name": "Customer database",
                        "organization_slug": "customer-org",
                        "region": "eu-west-1",
                        "status": "ACTIVE_HEALTHY",
                    }
                ],
            )
        if request.url.path == f"/v1/projects/{PROJECT_REF}/database/query/read-only":
            assert request.headers["authorization"] == "Bearer refreshed-access-token"
            body = json.loads(request.content)
            observed_queries.append(body)
            query = body["query"]
            if "FROM information_schema.tables" in query:
                return httpx.Response(
                    201,
                    json={
                        "result": [
                            {
                                "schema_name": "public",
                                "table_name": "Requests",
                                "table_type": "BASE TABLE",
                            }
                        ]
                    },
                )
            if "FROM information_schema.columns" in query:
                assert body["parameters"] == ["public", "Requests"]
                return httpx.Response(
                    201,
                    json={
                        "result": [
                            {
                                "name": "id",
                                "data_type": "bigint",
                                "nullable": False,
                                "ordinal_position": 1,
                            },
                            {
                                "name": "status",
                                "data_type": "text",
                                "nullable": False,
                                "ordinal_position": 2,
                            },
                        ]
                    },
                )
            assert 'FROM "public"."Requests"' in query
            assert 'SELECT "id", "status"' in query
            assert 'WHERE "status" = $1' in query
            assert "LIMIT 10" in query
            assert body["parameters"] == ["open"]
            return httpx.Response(
                201,
                json={"result": [{"id": 1, "status": "open"}]},
            )
        if request.url.path == "/v1/oauth/revoke":
            body = json.loads(request.content)
            assert body["client_id"] == "oauth-client-id"
            assert body["refresh_token"] == "rotated-refresh-token"
            return httpx.Response(204)
        raise AssertionError(f"Unexpected provider request: {request.method} {request.url}")

    settings.supabase_oauth_client_id = "oauth-client-id"
    settings.supabase_oauth_client_secret = SecretStr("oauth-client-secret")
    app = create_app(settings, supabase_management_transport=httpx.MockTransport(provider))

    with TestClient(app, raise_server_exceptions=False) as client:
        created_project = client.post(
            "/v1/admin/projects",
            headers=admin_headers,
            json={"name": "OAuth consumer"},
        )
        assert created_project.status_code == 201, created_project.text
        project = created_project.json()
        project_headers = {"X-API-Key": project["api_key"]}

        authorization = client.post(
            "/v1/connections/supabase/authorize",
            headers=project_headers,
            json={"organization_slug": "customer-org"},
        )
        assert authorization.status_code == 200, authorization.text
        authorization_url = authorization.json()["authorization_url"]
        parameters = parse_qs(urlparse(authorization_url).query)
        assert parameters["client_id"] == ["oauth-client-id"]
        assert parameters["code_challenge_method"] == ["S256"]
        assert parameters["organization_slug"] == ["customer-org"]
        assert "scope" not in parameters
        state = parameters["state"][0]

        with app.state.database.session_maker() as session:
            attempt = session.scalar(select(OAuthAttempt))
            assert attempt is not None
            assert state.encode() not in attempt.state_digest
            assert state.encode() not in attempt.encrypted_context

        callback = client.get(
            "/v1/connections/supabase/callback",
            params={"code": "provider-code", "state": state},
        )
        assert callback.status_code == 200, callback.text
        connection = callback.json()["connection"]
        connection_id = connection["id"]
        assert connection["status"] == "pending_project"
        assert connection["external_ref"] is None

        replay = client.get(
            "/v1/connections/supabase/callback",
            params={"code": "provider-code", "state": state},
        )
        assert replay.status_code == 422
        assert replay.json()["error"]["code"] == "invalid_request"

        projects = client.get(
            f"/v1/connections/supabase/{connection_id}/projects",
            headers=project_headers,
        )
        assert projects.status_code == 200, projects.text
        assert projects.json()[0]["ref"] == PROJECT_REF

        selected = client.post(
            f"/v1/connections/supabase/{connection_id}/select-project",
            headers=project_headers,
            json={"project_ref": PROJECT_REF},
        )
        assert selected.status_code == 200, selected.text
        assert selected.json()["status"] == "active"

        tables = client.get(
            f"/v1/connections/supabase/{connection_id}/tables",
            headers=project_headers,
        )
        assert tables.status_code == 200, tables.text
        assert tables.json() == [
            {"schema_name": "public", "table_name": "Requests", "kind": "table"}
        ]

        description = client.get(
            f"/v1/connections/supabase/{connection_id}/tables/public/Requests",
            headers=project_headers,
        )
        assert description.status_code == 200, description.text
        assert [item["name"] for item in description.json()["columns"]] == ["id", "status"]

        result = client.post(
            f"/v1/connections/supabase/{connection_id}/query",
            headers=project_headers,
            json={
                "schema_name": "public",
                "table_name": "Requests",
                "columns": ["id", "status"],
                "filters": [{"column": "status", "value": "open"}],
                "order": [{"column": "id", "direction": "asc"}],
                "limit": 10,
            },
        )
        assert result.status_code == 200, result.text
        assert result.json() == {
            "data": [{"id": 1, "status": "open"}],
            "returned": 1,
            "limit": 10,
        }

        disconnected = client.delete(
            f"/v1/connections/supabase/{connection_id}",
            headers=project_headers,
        )
        assert disconnected.status_code == 204, disconnected.text
        assert client.get("/v1/connections/supabase", headers=project_headers).json() == []

    assert len(observed_queries) >= 5
    with app.state.database.session_maker() as session:
        stored = session.get(ProviderConnection, connection_id)
        assert stored is not None
        assert stored.status == "disconnected"
        assert b"oauth-access-token" not in stored.encrypted_secret


def test_connection_routes_require_project_authentication(client: TestClient) -> None:
    response = client.get("/v1/connections/supabase")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


def test_oauth_start_requires_server_configuration(settings, admin_headers) -> None:
    settings.supabase_oauth_client_id = None
    settings.supabase_oauth_client_secret = None
    app = create_app(settings)

    with TestClient(app, raise_server_exceptions=False) as client:
        project = client.post(
            "/v1/admin/projects",
            headers=admin_headers,
            json={"name": "Unconfigured OAuth consumer"},
        ).json()
        response = client.post(
            "/v1/connections/supabase/authorize",
            headers={"X-API-Key": project["api_key"]},
            json={},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"


def test_catalog_identifiers_are_quoted_as_data() -> None:
    assert _quote_identifier('requests"; drop table audit;--') == (
        '"requests""; drop table audit;--"'
    )
