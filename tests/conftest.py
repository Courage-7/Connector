"""Shared fixtures for the focused connector-service architecture."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from connector_service.bootstrap.app import create_app
from connector_service.bootstrap.config import Settings

BEARER_TOKEN = "development-test-bearer-token-123456789"
PROJECT_REF = "abcdefghijklmnopqrst"


class SupabaseMock:
    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.url.path == "/v1/oauth/token":
            return httpx.Response(
                200,
                json={
                    "access_token": "provider-access-token",
                    "refresh_token": "provider-refresh-token",
                    "token_type": "Bearer",
                    "expires_in": 3600,
                },
            )
        if request.method == "POST" and request.url.path == "/v1/oauth/revoke":
            return httpx.Response(204)
        if request.method == "GET" and request.url.path == "/v1/projects":
            return httpx.Response(
                200,
                json=[
                    {
                        "id": PROJECT_REF,
                        "name": "Cooking Project",
                        "organization_slug": "connector-lab",
                        "region": "eu-west-1",
                        "status": "ACTIVE_HEALTHY",
                    }
                ],
            )
        if request.url.path == f"/v1/projects/{PROJECT_REF}/database/query/read-only":
            payload: dict[str, Any] = json.loads(request.content)
            query = payload["query"]
            if "information_schema.tables" in query:
                result = [
                    {
                        "schema_name": "public",
                        "table_name": "customers",
                        "table_type": "BASE TABLE",
                    }
                ]
            elif "information_schema.columns" in query:
                result = [
                    {
                        "name": "id",
                        "data_type": "uuid",
                        "nullable": False,
                        "ordinal_position": 1,
                    },
                    {
                        "name": "email",
                        "data_type": "text",
                        "nullable": False,
                        "ordinal_position": 2,
                    },
                ]
            else:
                result = [{"id": "customer-1", "email": "person@example.com"}]
            return httpx.Response(201, json=result)
        return httpx.Response(404, json={"path": request.url.path})


def make_settings(
    database_path: Path,
    *,
    subject: str = "user-one",
    encryption_key: str | None = None,
) -> Settings:
    return Settings(
        app_name="Connector Service",
        environment="test",
        database_url=f"sqlite+aiosqlite:///{database_path.as_posix()}",
        auto_create_schema=True,
        auth_mode="static",
        service_bearer_token=BEARER_TOKEN,
        development_subject=subject,
        token_encryption_key=encryption_key or Fernet.generate_key().decode(),
        supabase_oauth_client_id="oauth-client-id",
        supabase_oauth_client_secret="oauth-client-secret",
        supabase_oauth_redirect_uri="http://localhost:1080/v1/oauth/supabase/callback",
    )


@pytest.fixture
def database_path(tmp_path: Path) -> Path:
    return tmp_path / "control-plane.db"


@pytest.fixture
def settings(database_path: Path) -> Settings:
    return make_settings(database_path)


@pytest.fixture
def supabase_mock() -> SupabaseMock:
    return SupabaseMock()


@pytest.fixture
def client(
    settings: Settings,
    supabase_mock: SupabaseMock,
) -> Iterator[TestClient]:
    app = create_app(
        settings,
        supabase_transport=httpx.MockTransport(supabase_mock),
    )
    with TestClient(app, base_url="http://localhost:1080") as test_client:
        yield test_client


@pytest.fixture
def auth_headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {BEARER_TOKEN}"}


def connect_supabase(
    client: TestClient,
    auth_headers: dict[str, str],
) -> str:
    start = client.post(
        "/v1/connections/supabase/authorize",
        headers=auth_headers,
        json={},
    )
    assert start.status_code == 200
    authorization_url = httpx.URL(start.json()["authorization_url"])
    state = authorization_url.params["state"]
    callback = client.get(
        "/v1/oauth/supabase/callback",
        params={"code": "authorization-code", "state": state},
    )
    assert callback.status_code == 200
    return callback.json()["connection"]["id"]
