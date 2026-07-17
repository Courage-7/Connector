"""Real-provider integration tests for the Supabase connector."""

from __future__ import annotations

import json
import os
import secrets
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from cryptography.fernet import Fernet
from dotenv import load_dotenv
from fastapi.testclient import TestClient

from connector_service.app import create_app
from connector_service.config import Settings
from connector_service.connectors.supabase.schemas import validate_identifier


def _first_environment_value(*names: str) -> str:
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


@dataclass(frozen=True, slots=True)
class LiveConfig:
    project_url: str
    api_key: str
    authorization_token: str | None
    resource: str
    columns: tuple[str, ...]
    id_column: str | None
    limit: int

    @classmethod
    def from_environment(cls) -> LiveConfig:
        project_url = _first_environment_value("SUPABASE_URL", "SUPABASE_LIVE_URL")
        api_key = _first_environment_value(
            "SUPABASE_KEY",
            "SUPABASE_SECRET_KEY",
            "SUPABASE_SERVICE_ROLE_KEY",
            "SUPABASE_LIVE_API_KEY",
        )
        resource_value = _first_environment_value("SUPABASE_LIVE_RESOURCE")
        columns_value = _first_environment_value("SUPABASE_LIVE_COLUMNS")
        missing = []
        if not project_url:
            missing.append("SUPABASE_URL")
        if not api_key:
            missing.append("SUPABASE_KEY")
        if not resource_value:
            missing.append("SUPABASE_LIVE_RESOURCE")
        if not columns_value:
            missing.append("SUPABASE_LIVE_COLUMNS")
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")

        resource = validate_identifier(resource_value)
        columns = tuple(
            validate_identifier(value.strip())
            for value in columns_value.split(",")
            if value.strip()
        )
        if not columns:
            raise ValueError("SUPABASE_LIVE_COLUMNS must contain at least one column")
        if len(columns) != len(set(columns)):
            raise ValueError("SUPABASE_LIVE_COLUMNS must not contain duplicates")

        id_column_value = _first_environment_value("SUPABASE_LIVE_ID_COLUMN")
        id_column = validate_identifier(id_column_value) if id_column_value else None
        if id_column is not None and id_column not in columns:
            raise ValueError("SUPABASE_LIVE_ID_COLUMN must be included in SUPABASE_LIVE_COLUMNS")

        raw_limit = os.getenv("SUPABASE_LIVE_LIMIT", "5").strip()
        try:
            limit = int(raw_limit)
        except ValueError as exc:
            raise ValueError("SUPABASE_LIVE_LIMIT must be an integer") from exc
        if not 1 <= limit <= 25:
            raise ValueError("SUPABASE_LIVE_LIMIT must be between 1 and 25")

        authorization_token = os.getenv("SUPABASE_LIVE_AUTHORIZATION_TOKEN", "").strip() or None
        return cls(
            project_url=project_url,
            api_key=api_key,
            authorization_token=authorization_token,
            resource=resource,
            columns=columns,
            id_column=id_column,
            limit=limit,
        )


def run_live_integration(config: LiveConfig) -> dict[str, Any]:
    """Run the complete service path against the configured real provider."""

    checks: list[str] = []
    with TemporaryDirectory(prefix="connector-service-live-") as temporary_directory:
        database_path = Path(temporary_directory) / "live.db"
        admin_token = secrets.token_urlsafe(48)
        settings = Settings(
            environment="test",
            database_url=f"sqlite:///{database_path.as_posix()}",
            admin_token=admin_token,
            credential_encryption_key=Fernet.generate_key().decode(),
            cursor_signing_key=secrets.token_urlsafe(48),
            auto_create_schema=True,
            log_level="ERROR",
            max_page_size=25,
        )
        app = create_app(settings)
        with TestClient(app, raise_server_exceptions=False) as client:
            health = _expect_success(client.get("/health"))
            if health.get("status") != "ok":
                raise RuntimeError("health_check_failed: local service health check failed")
            checks.append("service_health")

            admin_headers = {"X-Admin-Token": admin_token}
            secret: dict[str, str] = {
                "project_url": config.project_url,
                "api_key": config.api_key,
            }
            if config.authorization_token:
                secret["authorization_token"] = config.authorization_token

            credential = _expect_success(
                client.post(
                    "/v1/admin/credentials",
                    headers=admin_headers,
                    json={
                        "name": "Live integration credential",
                        "connector": "supabase",
                        "secret": secret,
                    },
                )
            )
            project = _expect_success(
                client.post(
                    "/v1/admin/projects",
                    headers=admin_headers,
                    json={"name": "Live integration consumer"},
                )
            )
            actions = ["list_resources", "describe_resource", "list_rows"]
            if config.id_column:
                actions.append("get_row")
            grant = _expect_success(
                client.post(
                    "/v1/admin/grants",
                    headers=admin_headers,
                    json={
                        "project_id": project["id"],
                        "credential_id": credential["id"],
                        "connector": "supabase",
                        "actions": actions,
                        "policy": {
                            "resources": [
                                {
                                    "resource": config.resource,
                                    "columns": list(config.columns),
                                    "id_column": config.id_column,
                                    "max_page_size": config.limit,
                                }
                            ],
                            "rpcs": [],
                        },
                        "description": "Ephemeral real-provider integration grant",
                    },
                )
            )
            checks.extend(["encrypted_credential_provisioning", "project_api_key", "grant_policy"])

            action_headers = {"X-API-Key": project["api_key"]}
            action_base = {"grant_id": grant["id"]}
            resources_response = client.post(
                "/v1/actions/supabase/list_resources",
                headers=action_headers,
                json={**action_base, "input": {}},
            )
            resources = _expect_success(resources_response)
            if config.resource not in resources.get("data", []):
                raise RuntimeError("resource_policy_failed: configured resource was not listed")
            checks.append("resource_allowlist")

            description = _expect_success(
                client.post(
                    "/v1/actions/supabase/describe_resource",
                    headers=action_headers,
                    json={**action_base, "input": {"resource": config.resource}},
                )
            )
            if description.get("data", {}).get("columns") != list(config.columns):
                raise RuntimeError("resource_description_failed: configured columns did not match")
            checks.append("resource_description")

            first_response = client.post(
                "/v1/actions/supabase/list_rows",
                headers=action_headers,
                json={
                    **action_base,
                    "input": {
                        "resource": config.resource,
                        "columns": list(config.columns),
                        "limit": config.limit,
                    },
                },
            )
            first_page = _expect_success(first_response)
            checks.append("real_data_api_read")
            rows = first_page.get("data", [])
            pages_checked = 1

            next_cursor = first_page.get("meta", {}).get("next_cursor")
            if next_cursor:
                _expect_success(
                    client.post(
                        "/v1/actions/supabase/list_rows",
                        headers=action_headers,
                        json={
                            **action_base,
                            "input": {
                                "resource": config.resource,
                                "columns": list(config.columns),
                                "limit": config.limit,
                                "cursor": next_cursor,
                            },
                        },
                    )
                )
                pages_checked = 2
                checks.append("real_pagination")

            if config.id_column and rows:
                identifier = rows[0].get(config.id_column)
                if identifier is None:
                    raise RuntimeError("row_lookup_failed: configured identifier was null")
                _expect_success(
                    client.post(
                        "/v1/actions/supabase/get_row",
                        headers=action_headers,
                        json={
                            **action_base,
                            "input": {
                                "resource": config.resource,
                                "identifier": identifier,
                                "columns": list(config.columns),
                            },
                        },
                    )
                )
                checks.append("real_row_lookup")

            return {
                "status": "ok",
                "resource": config.resource,
                "rows_observed": len(rows),
                "pages_checked": pages_checked,
                "checks": checks,
                "request_id": first_response.headers.get("X-Request-ID"),
            }


def _expect_success(response: Any) -> dict[str, Any]:
    payload = response.json()
    if response.status_code >= 400:
        error = payload.get("error", {}) if isinstance(payload, dict) else {}
        code = error.get("code", "live_request_failed")
        message = error.get("message", "The live integration request failed safely.")
        raise RuntimeError(f"{code}: {message}")
    if not isinstance(payload, dict):
        raise RuntimeError("The service returned an unexpected response shape.")
    return payload


def load_live_environment() -> None:
    load_dotenv(".env", override=False)
    load_dotenv(".env.live", override=False)


def main() -> int:
    load_live_environment()
    try:
        config = LiveConfig.from_environment()
        result = run_live_integration(config)
    except (RuntimeError, ValueError) as exc:
        print(json.dumps({"status": "failed", "message": str(exc)}, separators=(",", ":")))
        return 1
    print(json.dumps(result, separators=(",", ":")))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
