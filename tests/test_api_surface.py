"""Public discovery, Swagger, and Bearer authentication tests."""

from conftest import BEARER_TOKEN
from fastapi.testclient import TestClient


def test_root_health_and_provider_catalog(client: TestClient) -> None:
    root = client.get("/", follow_redirects=False)
    assert root.status_code == 307
    assert root.headers["location"] == "/docs"
    assert client.get("/health").json()["status"] == "ok"

    response = client.get("/v1/providers")
    assert response.status_code == 200
    providers = {provider["name"]: provider for provider in response.json()}
    assert set(providers) == {"google_workspace", "microsoft_365", "supabase"}
    assert providers["supabase"]["status"] == "available"
    assert providers["supabase"]["configured"] is True
    assert providers["google_workspace"]["status"] == "planned"
    assert "teams" in providers["microsoft_365"]["capabilities"]

    supabase = client.get("/v1/providers/supabase")
    assert supabase.status_code == 200
    assert supabase.json()["display_name"] == "Supabase"
    tools = client.get("/v1/providers/supabase/tools")
    assert {tool["name"] for tool in tools.json()} == {
        "describe_table",
        "list_projects",
        "list_tables",
        "query_table",
        "select_project",
    }
    assert client.get("/v1/providers/unknown").status_code == 404


def test_openapi_has_one_simple_security_scheme(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    schemes = schema["components"]["securitySchemes"]
    assert set(schemes) == {"BearerAuth"}
    assert schemes["BearerAuth"]["scheme"] == "bearer"
    paths = set(schema["paths"])
    assert "/v1/admin/projects" not in paths
    assert "/v1/actions/{connector}/{action}" not in paths
    assert "/v1/connections/supabase/authorize" in paths
    assert "/v1/tools/supabase/query-table" in paths


def test_bearer_authentication(client: TestClient) -> None:
    missing = client.get("/v1/auth/me")
    assert missing.status_code == 401
    assert missing.headers["x-request-id"]

    invalid = client.get(
        "/v1/auth/me",
        headers={"Authorization": "Bearer incorrect"},
    )
    assert invalid.status_code == 401

    valid = client.get(
        "/v1/auth/me",
        headers={"Authorization": f"Bearer {BEARER_TOKEN}"},
    )
    assert valid.status_code == 200
    assert valid.json() == {
        "subject": "user-one",
        "tenant_id": "user-one",
        "authentication_method": "static_bearer",
    }


def test_mcp_discovery_and_authentication(client: TestClient) -> None:
    info = client.get("/v1/mcp")
    assert info.status_code == 200
    assert info.json()["endpoint"] == "/mcp"
    assert "supabase_query_table" in info.json()["tools"]

    unauthorized = client.post("/mcp", json={})
    assert unauthorized.status_code == 401
    assert unauthorized.headers["www-authenticate"] == "Bearer"

    mcp_headers = {
        "Authorization": f"Bearer {BEARER_TOKEN}",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": "2025-11-25",
    }
    initialized = client.post(
        "/mcp",
        headers=mcp_headers,
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2025-11-25",
                "capabilities": {},
                "clientInfo": {"name": "test-client", "version": "1.0"},
            },
        },
    )
    assert initialized.status_code == 200
    assert initialized.json()["result"]["serverInfo"]["name"] == "Connector Service"

    listed = client.post(
        "/mcp",
        headers=mcp_headers,
        json={"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
    )
    assert listed.status_code == 200
    names = {tool["name"] for tool in listed.json()["result"]["tools"]}
    assert "supabase_query_table" in names
