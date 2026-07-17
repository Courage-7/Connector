from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from connector_service.app import create_app
from connector_service.config import Settings


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        admin_token="admin-token-with-more-than-thirty-two-characters",
        credential_encryption_key=Fernet.generate_key().decode(),
        cursor_signing_key="cursor-key-with-more-than-thirty-two-characters",
        auto_create_schema=True,
        log_level="ERROR",
        provider_timeout_seconds=2,
        max_page_size=100,
    )


@pytest.fixture
def app(settings: Settings):
    return create_app(settings)


@pytest.fixture
def client(app) -> TestClient:
    with TestClient(app, raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def admin_headers(settings: Settings) -> dict[str, str]:
    return {"X-Admin-Token": settings.admin_token.get_secret_value()}


@pytest.fixture
def provision(client: TestClient, admin_headers: dict[str, str]) -> Callable[..., dict[str, Any]]:
    def _provision(
        *,
        actions: list[str] | None = None,
        resources: list[dict[str, Any]] | None = None,
        rpcs: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        credential_response = client.post(
            "/v1/admin/credentials",
            headers=admin_headers,
            json={
                "name": "Primary Supabase",
                "connector": "supabase",
                "secret": {
                    "project_url": "https://example.supabase.co",
                    "api_key": "provider-secret-key-with-sufficient-length",
                },
            },
        )
        assert credential_response.status_code == 201, credential_response.text
        project_response = client.post(
            "/v1/admin/projects",
            headers=admin_headers,
            json={"name": "Example Consumer"},
        )
        assert project_response.status_code == 201, project_response.text
        project = project_response.json()
        credential = credential_response.json()
        grant_response = client.post(
            "/v1/admin/grants",
            headers=admin_headers,
            json={
                "project_id": project["id"],
                "credential_id": credential["id"],
                "connector": "supabase",
                "actions": actions or ["list_resources", "describe_resource", "list_rows"],
                "policy": {
                    "resources": resources
                    or [
                        {
                            "resource": "documents",
                            "columns": ["id", "title", "status"],
                            "filter_columns": ["status"],
                            "order_columns": ["id", "title"],
                            "id_column": "id",
                            "max_page_size": 25,
                        }
                    ],
                    "rpcs": rpcs or [],
                },
                "description": "Test policy",
            },
        )
        assert grant_response.status_code == 201, grant_response.text
        return {
            "credential": credential,
            "project": project,
            "grant": grant_response.json(),
            "consumer_headers": {"X-API-Key": project["api_key"]},
        }

    return _provision
