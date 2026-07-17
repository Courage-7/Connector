from __future__ import annotations

import pytest

from connector_service.tools.live_supabase import LiveConfig

REQUIRED_ENVIRONMENT = {
    "SUPABASE_URL": "https://example.supabase.co",
    "SUPABASE_KEY": "sb_secret_backend-key-with-sufficient-length",
    "SUPABASE_LIVE_RESOURCE": "documents",
    "SUPABASE_LIVE_COLUMNS": "id,title",
}


def test_live_config_parses_safe_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in REQUIRED_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("SUPABASE_LIVE_LIMIT", "3")
    monkeypatch.setenv("SUPABASE_LIVE_ID_COLUMN", "id")

    config = LiveConfig.from_environment()

    assert config.resource == "documents"
    assert config.columns == ("id", "title")
    assert config.limit == 3
    assert config.id_column == "id"
    assert config.authorization_token is None


def test_live_config_reports_names_without_secret_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in REQUIRED_ENVIRONMENT:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_LIVE_API_KEY", raising=False)

    with pytest.raises(ValueError) as error:
        LiveConfig.from_environment()

    message = str(error.value)
    assert "SUPABASE_KEY" in message
    assert "sb_secret" not in message


def test_live_config_rejects_unsafe_identifier(monkeypatch: pytest.MonkeyPatch) -> None:
    for name, value in REQUIRED_ENVIRONMENT.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("SUPABASE_LIVE_RESOURCE", "documents?select=*")

    with pytest.raises(ValueError):
        LiveConfig.from_environment()
