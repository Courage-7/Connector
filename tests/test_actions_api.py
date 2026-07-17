from __future__ import annotations

import json
from typing import Any

import httpx
from fastapi.testclient import TestClient

from connector_service.connectors.supabase.connector import SupabaseConnector


def install_transport(app, settings, handler) -> None:
    connector = SupabaseConnector(
        settings,
        app.state.cursor_codec,
        transport=httpx.MockTransport(handler),
    )
    app.state.registry.register(connector, replace=True)


def test_list_resources_uses_local_policy_without_provider(client: TestClient, provision) -> None:
    result = provision(actions=["list_resources"])

    response = client.post(
        "/v1/actions/supabase/list_resources",
        headers=result["consumer_headers"],
        json={"grant_id": result["grant"]["id"], "input": {}},
    )

    assert response.status_code == 200
    assert response.json()["data"] == ["documents"]


def test_action_requires_project_api_key(client: TestClient) -> None:
    response = client.post(
        "/v1/actions/supabase/list_resources",
        json={"grant_id": "missing", "input": {}},
    )

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


def test_grant_prevents_unapproved_action(client: TestClient, provision) -> None:
    result = provision(actions=["list_resources"])

    response = client.post(
        "/v1/actions/supabase/list_rows",
        headers=result["consumer_headers"],
        json={"grant_id": result["grant"]["id"], "input": {"resource": "documents"}},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "action_not_allowed"


def test_list_rows_enforces_policy_and_returns_signed_cursor(
    client: TestClient, app, settings, provision
) -> None:
    observed: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        observed["url"] = str(request.url)
        observed["apikey"] = request.headers["apikey"]
        observed["authorization"] = request.headers.get("Authorization")
        return httpx.Response(
            200,
            json=[
                {"id": 1, "title": "One", "status": "active"},
                {"id": 2, "title": "Two", "status": "active"},
            ],
        )

    install_transport(app, settings, handler)
    result = provision(actions=["list_rows"])
    response = client.post(
        "/v1/actions/supabase/list_rows",
        headers=result["consumer_headers"],
        json={
            "grant_id": result["grant"]["id"],
            "input": {
                "resource": "documents",
                "columns": ["id", "title", "status"],
                "filters": [{"column": "status", "operator": "eq", "value": "active"}],
                "order": [{"column": "id", "direction": "asc"}],
                "limit": 2,
            },
        },
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["meta"]["returned"] == 2
    assert body["meta"]["next_cursor"]
    assert observed["apikey"] == "provider-secret-key-with-sufficient-length"
    assert observed["authorization"] is None
    assert "/rest/v1/documents" in observed["url"]
    assert "status=eq.active" in observed["url"]


def test_cursor_cannot_be_reused_for_a_different_query(
    client: TestClient, app, settings, provision
) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[{"id": 1}, {"id": 2}])

    install_transport(app, settings, handler)
    result = provision(actions=["list_rows"])
    initial = client.post(
        "/v1/actions/supabase/list_rows",
        headers=result["consumer_headers"],
        json={
            "grant_id": result["grant"]["id"],
            "input": {"resource": "documents", "columns": ["id"], "limit": 2},
        },
    ).json()

    response = client.post(
        "/v1/actions/supabase/list_rows",
        headers=result["consumer_headers"],
        json={
            "grant_id": result["grant"]["id"],
            "input": {
                "resource": "documents",
                "columns": ["id", "title"],
                "limit": 2,
                "cursor": initial["meta"]["next_cursor"],
            },
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_cursor"


def test_unapproved_column_is_rejected_before_provider_call(
    client: TestClient, app, settings, provision
) -> None:
    called = False

    def handler(_request: httpx.Request) -> httpx.Response:
        nonlocal called
        called = True
        return httpx.Response(200, json=[])

    install_transport(app, settings, handler)
    result = provision(actions=["list_rows"])
    response = client.post(
        "/v1/actions/supabase/list_rows",
        headers=result["consumer_headers"],
        json={
            "grant_id": result["grant"]["id"],
            "input": {"resource": "documents", "columns": ["private_notes"]},
        },
    )

    assert response.status_code == 403
    assert not called


def test_provider_error_body_is_not_leaked(client: TestClient, app, settings, provision) -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"message": "sensitive database policy and table details"},
        )

    install_transport(app, settings, handler)
    result = provision(actions=["list_rows"])
    response = client.post(
        "/v1/actions/supabase/list_rows",
        headers=result["consumer_headers"],
        json={"grant_id": result["grant"]["id"], "input": {"resource": "documents"}},
    )

    assert response.status_code == 502
    assert response.json()["error"]["code"] == "provider_access_denied"
    assert "sensitive" not in json.dumps(response.json())


def test_get_row_and_rpc_are_explicitly_allowlisted(
    client: TestClient, app, settings, provision
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "/rpc/search_documents" in str(request.url):
            assert json.loads(request.content) == {"query_text": "hello"}
            return httpx.Response(200, json=[{"id": 7, "title": "Match"}])
        return httpx.Response(200, json=[{"id": 7, "title": "Match", "status": "active"}])

    install_transport(app, settings, handler)
    result = provision(
        actions=["get_row", "call_rpc"],
        rpcs=[
            {
                "name": "search_documents",
                "allowed_arguments": ["query_text"],
                "max_rows": 10,
            }
        ],
    )

    row_response = client.post(
        "/v1/actions/supabase/get_row",
        headers=result["consumer_headers"],
        json={
            "grant_id": result["grant"]["id"],
            "input": {"resource": "documents", "identifier": 7, "columns": ["id", "title"]},
        },
    )
    rpc_response = client.post(
        "/v1/actions/supabase/call_rpc",
        headers=result["consumer_headers"],
        json={
            "grant_id": result["grant"]["id"],
            "input": {"rpc": "search_documents", "arguments": {"query_text": "hello"}},
        },
    )

    assert row_response.status_code == 200
    assert row_response.json()["data"]["id"] == 7
    assert rpc_response.status_code == 200
    assert rpc_response.json()["meta"]["returned"] == 1
