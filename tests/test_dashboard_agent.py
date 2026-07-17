from __future__ import annotations

from datetime import UTC, datetime, timedelta

import httpx
from fastapi.testclient import TestClient
from sqlalchemy import select

from connector_service.app import create_app
from connector_service.db.models import (
    DashboardLoginTicket,
    ProviderConnection,
)

PROJECT_REF = "abcdefghijklmnopqrst"


def _create_consumer(client: TestClient, admin_headers: dict[str, str]) -> dict[str, str]:
    response = client.post(
        "/v1/admin/projects",
        headers=admin_headers,
        json={"name": "Dashboard consumer"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_dashboard_session(client: TestClient, api_key: str) -> str:
    ticket_response = client.post(
        "/v1/dashboard/login-tickets",
        headers={"X-API-Key": api_key},
        json={"return_to": "/app/"},
    )
    assert ticket_response.status_code == 200, ticket_response.text
    exchange = client.get(
        ticket_response.json()["login_url"],
        follow_redirects=False,
    )
    assert exchange.status_code == 303, exchange.text
    csrf = client.cookies.get("connector_dashboard_csrf")
    assert csrf
    assert client.cookies.get("connector_dashboard_session")
    return csrf


def test_dashboard_login_ticket_is_single_use_and_session_is_csrf_protected(
    app,
    client: TestClient,
    admin_headers: dict[str, str],
) -> None:
    consumer = _create_consumer(client, admin_headers)
    ticket_response = client.post(
        "/v1/dashboard/login-tickets",
        headers={"X-API-Key": consumer["api_key"]},
        json={"return_to": "/app/"},
    )
    assert ticket_response.status_code == 200, ticket_response.text
    ticket = ticket_response.json()["ticket"]

    with app.state.database.session_maker() as session:
        stored = session.scalar(select(DashboardLoginTicket))
        assert stored is not None
        assert ticket.encode() not in stored.token_digest

    exchange = client.get(ticket_response.json()["login_url"], follow_redirects=False)
    assert exchange.status_code == 303
    assert exchange.headers["location"] == "/app/"
    dashboard_session = client.get("/v1/dashboard/session")
    assert dashboard_session.status_code == 200, dashboard_session.text
    assert dashboard_session.json()["project"]["id"] == consumer["id"]

    replay = client.get(ticket_response.json()["login_url"], follow_redirects=False)
    assert replay.status_code == 422

    missing_csrf = client.delete("/v1/dashboard/session")
    assert missing_csrf.status_code == 401
    csrf = client.cookies.get("connector_dashboard_csrf")
    revoked = client.delete(
        "/v1/dashboard/session",
        headers={"X-CSRF-Token": csrf},
    )
    assert revoked.status_code == 204
    assert client.get("/v1/dashboard/session").status_code == 401


def test_agent_query_requires_dashboard_approval_and_writes_redacted_audit(
    settings,
    admin_headers: dict[str, str],
) -> None:
    observed_data_queries: list[str] = []

    def provider(request: httpx.Request) -> httpx.Response:
        if request.url.path != f"/v1/projects/{PROJECT_REF}/database/query/read-only":
            raise AssertionError(f"Unexpected provider request: {request.method} {request.url}")
        body = __import__("json").loads(request.content)
        query = body["query"]
        if "FROM information_schema.tables" in query:
            return httpx.Response(
                200,
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
            return httpx.Response(
                200,
                json={
                    "result": [
                        {
                            "name": "id",
                            "data_type": "uuid",
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
        observed_data_queries.append(query)
        return httpx.Response(200, json={"result": [{"id": "row-1", "status": "open"}]})

    app = create_app(settings, supabase_management_transport=httpx.MockTransport(provider))
    with TestClient(app, raise_server_exceptions=False) as client:
        consumer = _create_consumer(client, admin_headers)
        with app.state.database.session_maker() as session:
            connection = ProviderConnection(
                project_id=consumer["id"],
                connector="supabase",
                external_ref=PROJECT_REF,
                name="Customer database",
                status="active",
                encrypted_secret=app.state.credential_cipher.encrypt(
                    {
                        "access_token": "access-token",
                        "refresh_token": "refresh-token",
                        "token_type": "Bearer",
                        "expires_at": (datetime.now(UTC) + timedelta(hours=1)).isoformat(),
                    }
                ),
                token_expires_at=datetime.now(UTC) + timedelta(hours=1),
            )
            session.add(connection)
            session.commit()
            connection_id = connection.id

        project_headers = {"X-API-Key": consumer["api_key"]}
        requested = client.post(
            f"/v1/agent/connections/{connection_id}/query-requests",
            headers=project_headers,
            json={
                "schema_name": "public",
                "table_name": "Requests",
                "columns": ["id", "status"],
                "filters": [{"column": "status", "value": "open"}],
                "limit": 10,
            },
        )
        assert requested.status_code == 200, requested.text
        query_request_id = requested.json()["id"]
        assert requested.json()["status"] == "pending"
        assert observed_data_queries == []

        blocked = client.post(
            f"/v1/agent/query-requests/{query_request_id}/execute",
            headers=project_headers,
        )
        assert blocked.status_code == 409

        csrf = _create_dashboard_session(client, consumer["api_key"])
        approved = client.post(
            f"/v1/dashboard/query-requests/{query_request_id}/approve",
            headers={"X-CSRF-Token": csrf},
            json={"note": "Approved for the current task."},
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["status"] == "approved"

        executed = client.post(
            f"/v1/agent/query-requests/{query_request_id}/execute",
            headers=project_headers,
        )
        assert executed.status_code == 200, executed.text
        assert executed.json()["data"] == [{"id": "row-1", "status": "open"}]
        assert len(observed_data_queries) == 1

        audit = client.get("/v1/dashboard/audit")
        assert audit.status_code == 200, audit.text
        assert audit.json()[0]["actor_type"] == "agent"
        assert audit.json()[0]["returned_rows"] == 1
        assert audit.json()[0]["filters"] == [{"column": "status", "value_present": True}]
        assert "open" not in audit.text
