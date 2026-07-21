"""Persistence and owner-boundary tests."""

from __future__ import annotations

from pathlib import Path

import httpx
from conftest import BEARER_TOKEN, SupabaseMock, connect_supabase, make_settings
from fastapi.testclient import TestClient

from connector_service.bootstrap.app import create_app


def test_connection_survives_restart_and_is_owner_scoped(
    database_path: Path,
    auth_headers: dict[str, str],
) -> None:
    encryption_key = "fO3EnZIbErWIx1ltO7MVIyZ1m2FKHWAxWzp8gW0vJ7Y="
    transport = httpx.MockTransport(SupabaseMock())
    first_settings = make_settings(
        database_path,
        subject="owner-a",
        encryption_key=encryption_key,
    )
    with TestClient(create_app(first_settings, supabase_transport=transport)) as first:
        connection_id = connect_supabase(first, auth_headers)

    restarted_settings = make_settings(
        database_path,
        subject="owner-a",
        encryption_key=encryption_key,
    )
    with TestClient(create_app(restarted_settings, supabase_transport=transport)) as restarted:
        rows = restarted.get("/v1/connections", headers=auth_headers).json()
        assert [row["id"] for row in rows] == [connection_id]

    other_settings = make_settings(
        database_path,
        subject="owner-b",
        encryption_key=encryption_key,
    )
    with TestClient(create_app(other_settings, supabase_transport=transport)) as other:
        assert other.get("/v1/connections", headers=auth_headers).json() == []
        hidden = other.get(
            f"/v1/connections/{connection_id}",
            headers={"Authorization": f"Bearer {BEARER_TOKEN}"},
        )
        assert hidden.status_code == 404
