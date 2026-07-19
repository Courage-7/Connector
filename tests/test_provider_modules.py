from __future__ import annotations

import pytest
from pydantic import ValidationError

from connector_service.app import create_app
from connector_service.config import Settings
from connector_service.providers.catalog import ProviderCapability


@pytest.mark.parametrize(
    ("enabled", "expected", "registered_connectors"),
    [
        ("supabase", {"supabase"}, {"supabase"}),
        ("gmail", {"gmail"}, set()),
        ("outlook", {"outlook"}, set()),
        ("gmail,outlook", {"gmail", "outlook"}, set()),
        (
            "supabase,outlook,gmail",
            {"gmail", "outlook", "supabase"},
            {"supabase"},
        ),
    ],
)
def test_app_constructs_only_selected_provider_modules(
    settings: Settings,
    enabled: str,
    expected: set[str],
    registered_connectors: set[str],
) -> None:
    selected = Settings(**{**settings.model_dump(), "enabled_providers": enabled})
    app = create_app(selected)

    assert app.state.providers.enabled_names == expected
    assert set(app.state.registry.catalog()) == registered_connectors

    paths = app.openapi()["paths"]
    has_database = "supabase" in expected
    has_email = bool(expected.intersection({"gmail", "outlook"}))
    assert ("/v1/connections/supabase/authorize" in paths) is has_database
    assert ("/v1/connections/{provider}/authorize" in paths) is has_email
    assert ("/v1/connections/{provider}/{connection_id}/calendar/events" in paths) is has_email
    assert ("/v1/connections/outlook/{connection_id}/teams" in paths) is ("outlook" in expected)
    assert ("/v1/actions/{connector}/{action}" in paths) is has_database


def test_provider_capabilities_are_discoverable(settings: Settings) -> None:
    app = create_app(settings)

    gmail = app.state.providers.get("gmail")
    outlook = app.state.providers.get("outlook")
    supabase = app.state.providers.get("supabase")

    assert ProviderCapability.EMAIL_SEND in gmail.capabilities
    assert ProviderCapability.EMAIL_SEND in outlook.capabilities
    assert ProviderCapability.CALENDAR in gmail.capabilities
    assert ProviderCapability.CALENDAR in outlook.capabilities
    assert ProviderCapability.TEAMS in outlook.capabilities
    assert ProviderCapability.DATABASE in supabase.capabilities
    assert ProviderCapability.ACTIONS in supabase.capabilities


def test_enabled_provider_setting_rejects_unknown_modules(settings: Settings) -> None:
    with pytest.raises(ValidationError, match="unsupported providers"):
        Settings(**{**settings.model_dump(), "enabled_providers": "gmail,unknown"})


def test_provider_discovery_returns_enabled_modules(client, provision) -> None:
    workspace = provision()

    response = client.get("/v1/providers", headers=workspace["consumer_headers"])

    assert response.status_code == 200
    assert {item["name"] for item in response.json()} == {
        "gmail",
        "outlook",
        "supabase",
    }


def test_swagger_and_openapi_expose_authentication(client) -> None:
    docs = client.get("/docs")
    redoc = client.get("/redoc")
    schema = client.get("/openapi.json")

    assert docs.status_code == 200
    assert "Swagger UI" in docs.text
    assert redoc.status_code == 200
    assert schema.status_code == 200
    security_schemes = schema.json()["components"]["securitySchemes"]
    assert security_schemes["AdminToken"]["name"] == "X-Admin-Token"
    assert security_schemes["ProjectApiKey"]["name"] == "X-API-Key"
