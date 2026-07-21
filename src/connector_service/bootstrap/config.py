"""Validated runtime configuration for the connector service."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from cryptography.fernet import Fernet
from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Process configuration loaded from generic environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="",
        extra="ignore",
    )

    app_name: str = "Connector Service"
    environment: Literal["development", "test", "production"] = "production"
    log_level: str = "INFO"
    database_url: str
    auto_create_schema: bool = False

    auth_mode: Literal["static", "supabase_jwt"] = "static"
    service_bearer_token: SecretStr | None = None
    development_subject: str = "local-development-user"
    supabase_auth_url: str | None = None
    supabase_auth_audience: str = "authenticated"
    jwks_cache_seconds: int = Field(default=300, ge=30, le=3600)

    token_encryption_key: SecretStr
    oauth_transaction_ttl_seconds: int = Field(default=600, ge=60, le=1800)
    provider_timeout_seconds: float = Field(default=15.0, gt=0, le=60)
    max_provider_response_bytes: int = Field(
        default=5 * 1024 * 1024,
        ge=1024,
        le=50 * 1024 * 1024,
    )
    supabase_oauth_client_id: str | None = None
    supabase_oauth_client_secret: SecretStr | None = None
    supabase_oauth_redirect_uri: str = "http://localhost:1080/v1/oauth/supabase/callback"
    supabase_management_api_url: str = "https://api.supabase.com"
    supabase_oauth_token_skew_seconds: int = Field(default=60, ge=0, le=300)

    outlook_oauth_client_id: str | None = None
    outlook_oauth_client_secret: SecretStr | None = None
    outlook_oauth_redirect_uri: str = "http://localhost:1080/v1/oauth/microsoft_365/callback"
    outlook_oauth_authority: str = "https://login.microsoftonline.com/common/oauth2/v2.0"
    outlook_graph_api_url: str = "https://graph.microsoft.com/v1.0"

    gmail_oauth_client_id: str | None = None
    gmail_oauth_client_secret: SecretStr | None = None
    gmail_oauth_redirect_uri: str = "http://localhost:1080/v1/oauth/google_workspace/callback"
    gmail_oauth_authority: str = "https://accounts.google.com/o/oauth2/v2"
    gmail_token_url: str = "https://oauth2.googleapis.com"
    gmail_userinfo_url: str = "https://openidconnect.googleapis.com/v1"
    gmail_api_url: str = "https://gmail.googleapis.com/gmail/v1"
    google_calendar_api_url: str = "https://www.googleapis.com/calendar/v3"

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("unsupported log level")
        return normalized

    @field_validator("database_url")
    @classmethod
    def validate_database_url(cls, value: str) -> str:
        normalized = value.strip()
        if normalized.startswith("postgres://"):
            normalized = "postgresql://" + normalized.removeprefix("postgres://")
        if not normalized:
            raise ValueError("database_url must not be empty")
        return normalized

    @field_validator("token_encryption_key")
    @classmethod
    def validate_token_encryption_key(cls, value: SecretStr) -> SecretStr:
        try:
            Fernet(value.get_secret_value().encode("ascii"))
        except (ValueError, UnicodeEncodeError) as exc:
            raise ValueError("TOKEN_ENCRYPTION_KEY must be a valid Fernet key") from exc
        return value

    @property
    def async_database_url(self) -> str:
        if self.database_url.startswith("postgresql+psycopg://"):
            return self.database_url
        if self.database_url.startswith("postgresql://"):
            return self.database_url.replace("postgresql://", "postgresql+psycopg://", 1)
        return self.database_url

    @property
    def supabase_oauth_configured(self) -> bool:
        return bool(self.supabase_oauth_client_id and self.supabase_oauth_client_secret is not None)

    @property
    def google_workspace_configured(self) -> bool:
        return bool(self.gmail_oauth_client_id and self.gmail_oauth_client_secret)

    @property
    def microsoft_365_configured(self) -> bool:
        return bool(self.outlook_oauth_client_id and self.outlook_oauth_client_secret)

    @model_validator(mode="after")
    def validate_runtime(self) -> Settings:
        if self.environment != "test" and not self.database_url.startswith("postgresql"):
            raise ValueError("development and production require a PostgreSQL DATABASE_URL")
        if self.auth_mode == "static" and self.service_bearer_token is None:
            raise ValueError("SERVICE_BEARER_TOKEN is required when AUTH_MODE=static")
        if (
            self.auth_mode == "static"
            and self.service_bearer_token is not None
            and len(self.service_bearer_token.get_secret_value()) < 32
        ):
            raise ValueError("SERVICE_BEARER_TOKEN must contain at least 32 characters")
        if self.auth_mode == "supabase_jwt" and not self.supabase_auth_url:
            raise ValueError("SUPABASE_AUTH_URL is required when AUTH_MODE=supabase_jwt")
        if self.environment == "production" and self.auth_mode == "static":
            raise ValueError("static bearer authentication is not allowed in production")
        self._validate_oauth_pair(
            "supabase",
            self.supabase_oauth_client_id,
            self.supabase_oauth_client_secret,
        )
        self._validate_oauth_pair(
            "google_workspace",
            self.gmail_oauth_client_id,
            self.gmail_oauth_client_secret,
        )
        self._validate_oauth_pair(
            "microsoft_365",
            self.outlook_oauth_client_id,
            self.outlook_oauth_client_secret,
        )
        return self

    @staticmethod
    def _validate_oauth_pair(
        name: str,
        client_id: str | None,
        client_secret: SecretStr | None,
    ) -> None:
        if bool(client_id) != (client_secret is not None):
            raise ValueError(
                f"{name} OAuth client ID and client secret must be configured together"
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
