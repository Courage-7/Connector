"""Application configuration loaded from environment variables."""

from __future__ import annotations

from functools import lru_cache

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SUPPORTED_PROVIDERS = frozenset({"gmail", "outlook", "supabase"})


class Settings(BaseSettings):
    """Validated runtime configuration.

    Secret values intentionally have no defaults so a deployment cannot start with known keys.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="CONNECTOR_",
        extra="ignore",
    )

    app_name: str = "Connector"
    environment: str = "production"
    database_url: str = "sqlite:///./connector_service.db"
    admin_token: SecretStr
    credential_encryption_key: SecretStr
    cursor_signing_key: SecretStr
    auto_create_schema: bool = False
    log_level: str = "INFO"
    provider_timeout_seconds: float = Field(default=15.0, gt=0, le=60)
    provider_max_retries: int = Field(default=2, ge=0, le=5)
    provider_retry_base_seconds: float = Field(default=0.25, ge=0, le=5)
    max_provider_response_bytes: int = Field(default=5 * 1024 * 1024, ge=1024, le=50 * 1024 * 1024)
    max_page_size: int = Field(default=100, ge=1, le=1000)
    enabled_providers: str = "supabase,outlook,gmail"
    supabase_oauth_client_id: str | None = None
    supabase_oauth_client_secret: SecretStr | None = None
    supabase_oauth_redirect_uri: str = "http://localhost:8000/v1/connections/supabase/callback"
    supabase_management_api_url: str = "https://api.supabase.com"
    supabase_oauth_attempt_ttl_seconds: int = Field(default=600, ge=60, le=1800)
    supabase_oauth_token_skew_seconds: int = Field(default=60, ge=0, le=300)
    email_oauth_attempt_ttl_seconds: int = Field(default=600, ge=60, le=1800)
    email_oauth_token_skew_seconds: int = Field(default=60, ge=0, le=300)
    email_send_approval_ttl_seconds: int = Field(default=30 * 60, ge=60, le=24 * 60 * 60)
    outlook_oauth_client_id: str | None = None
    outlook_oauth_client_secret: SecretStr | None = None
    outlook_oauth_redirect_uri: str = "http://localhost:8000/v1/connections/outlook/callback"
    outlook_oauth_authority: str = "https://login.microsoftonline.com/common/oauth2/v2.0"
    outlook_graph_api_url: str = "https://graph.microsoft.com/v1.0"
    gmail_oauth_client_id: str | None = None
    gmail_oauth_client_secret: SecretStr | None = None
    gmail_oauth_redirect_uri: str = "http://localhost:8000/v1/connections/gmail/callback"
    gmail_oauth_authority: str = "https://accounts.google.com/o/oauth2/v2"
    gmail_token_url: str = "https://oauth2.googleapis.com"
    gmail_userinfo_url: str = "https://openidconnect.googleapis.com/v1"
    gmail_api_url: str = "https://gmail.googleapis.com/gmail/v1"
    dashboard_login_ticket_ttl_seconds: int = Field(default=120, ge=30, le=600)
    dashboard_session_ttl_seconds: int = Field(default=8 * 60 * 60, ge=300, le=7 * 24 * 60 * 60)

    @field_validator("admin_token", "cursor_signing_key")
    @classmethod
    def validate_secret_length(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("must contain at least 32 characters")
        return value

    @field_validator("environment")
    @classmethod
    def normalize_environment(cls, value: str) -> str:
        normalized = value.strip().lower()
        if normalized not in {"development", "test", "production"}:
            raise ValueError("must be development, test, or production")
        return normalized

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.strip().upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("unsupported log level")
        return normalized

    @field_validator("enabled_providers")
    @classmethod
    def normalize_enabled_providers(cls, value: str) -> str:
        names = [item.strip().lower() for item in value.split(",") if item.strip()]
        if not names:
            raise ValueError("at least one provider must be enabled")
        unknown = sorted(set(names) - SUPPORTED_PROVIDERS)
        if unknown:
            raise ValueError(f"unsupported providers: {', '.join(unknown)}")
        return ",".join(dict.fromkeys(names))

    @property
    def enabled_provider_names(self) -> tuple[str, ...]:
        return tuple(self.enabled_providers.split(","))

    @model_validator(mode="after")
    def validate_supabase_oauth_configuration(self) -> Settings:
        has_client_id = bool(self.supabase_oauth_client_id)
        has_client_secret = self.supabase_oauth_client_secret is not None
        if has_client_id != has_client_secret:
            message = (
                "supabase_oauth_client_id and supabase_oauth_client_secret "
                "must be configured together"
            )
            raise ValueError(message)
        if not self.supabase_management_api_url.startswith("https://"):
            raise ValueError("supabase_management_api_url must use HTTPS")
        if not (
            self.supabase_oauth_redirect_uri.startswith("https://")
            or self.supabase_oauth_redirect_uri.startswith("http://127.0.0.1")
            or self.supabase_oauth_redirect_uri.startswith("http://localhost")
        ):
            raise ValueError("supabase_oauth_redirect_uri must use HTTPS outside local development")
        self._validate_oauth_pair(
            "outlook",
            self.outlook_oauth_client_id,
            self.outlook_oauth_client_secret,
        )
        self._validate_oauth_pair(
            "gmail",
            self.gmail_oauth_client_id,
            self.gmail_oauth_client_secret,
        )
        for name, value in {
            "outlook_oauth_authority": self.outlook_oauth_authority,
            "outlook_graph_api_url": self.outlook_graph_api_url,
            "gmail_oauth_authority": self.gmail_oauth_authority,
            "gmail_token_url": self.gmail_token_url,
            "gmail_userinfo_url": self.gmail_userinfo_url,
            "gmail_api_url": self.gmail_api_url,
        }.items():
            if not value.startswith("https://"):
                raise ValueError(f"{name} must use HTTPS")
        for name, value in {
            "outlook_oauth_redirect_uri": self.outlook_oauth_redirect_uri,
            "gmail_oauth_redirect_uri": self.gmail_oauth_redirect_uri,
        }.items():
            if not self._is_secure_redirect(value):
                raise ValueError(f"{name} must use HTTPS outside local development")
        return self

    @staticmethod
    def _validate_oauth_pair(
        provider: str,
        client_id: str | None,
        client_secret: SecretStr | None,
    ) -> None:
        if bool(client_id) != (client_secret is not None):
            raise ValueError(
                f"{provider}_oauth_client_id and {provider}_oauth_client_secret "
                "must be configured together"
            )

    @staticmethod
    def _is_secure_redirect(value: str) -> bool:
        return (
            value.startswith("https://")
            or value.startswith("http://127.0.0.1")
            or value.startswith("http://localhost")
        )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings instance."""

    return Settings()  # type: ignore[call-arg]
