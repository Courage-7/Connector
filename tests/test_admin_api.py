from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import select

from connector_service.db.models import Credential, ProjectApiKey


def test_health_is_public_and_correlated(client: TestClient) -> None:
    response = client.get("/health", headers={"X-Request-ID": "test-request"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0"}
    assert response.headers["X-Request-ID"] == "test-request"


def test_admin_routes_require_valid_token(client: TestClient) -> None:
    response = client.post("/v1/admin/projects", json={"name": "Denied"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "authentication_failed"


def test_provisioning_never_persists_plaintext_secrets(client: TestClient, app, provision) -> None:
    result = provision()

    with app.state.database.session_maker() as session:
        credential = session.scalar(select(Credential))
        api_key = session.scalar(select(ProjectApiKey))

    assert credential is not None
    assert b"provider-secret-key" not in credential.encrypted_secret
    assert api_key is not None
    assert result["project"]["api_key"].encode() not in api_key.digest


def test_duplicate_project_name_returns_conflict(
    client: TestClient, admin_headers: dict[str, str]
) -> None:
    body = {"name": "Unique Consumer"}
    assert client.post("/v1/admin/projects", headers=admin_headers, json=body).status_code == 201

    response = client.post("/v1/admin/projects", headers=admin_headers, json=body)

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "conflict"


def test_grant_rejects_unknown_actions(client: TestClient, admin_headers: dict[str, str]) -> None:
    credential = client.post(
        "/v1/admin/credentials",
        headers=admin_headers,
        json={
            "name": "Provider",
            "connector": "supabase",
            "secret": {
                "project_url": "https://example.supabase.co",
                "api_key": "provider-secret-key-with-sufficient-length",
            },
        },
    ).json()
    project = client.post(
        "/v1/admin/projects", headers=admin_headers, json={"name": "Consumer"}
    ).json()

    response = client.post(
        "/v1/admin/grants",
        headers=admin_headers,
        json={
            "project_id": project["id"],
            "credential_id": credential["id"],
            "connector": "supabase",
            "actions": ["delete_rows"],
            "policy": {"resources": [], "rpcs": []},
        },
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "invalid_request"
