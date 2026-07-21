"""Provider-neutral connection lifecycle with the Supabase OAuth slice."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from connector_service.bootstrap.config import Settings
from connector_service.connections.oauth import create_oauth_material, digest_oauth_state
from connector_service.connections.repository import ConnectionRepository
from connector_service.connections.schemas import (
    AuthorizationStartResponse,
    ConnectionResponse,
    OAuthCallbackResponse,
)
from connector_service.core.exceptions import InvalidRequestError
from connector_service.identity.principal import Principal
from connector_service.infrastructure.crypto import SecretCipher
from connector_service.infrastructure.database.models import ProviderConnection
from connector_service.providers.supabase.management import (
    OAuthTokens,
    SupabaseManagementClient,
)


class ConnectionService:
    def __init__(
        self,
        *,
        settings: Settings,
        cipher: SecretCipher,
        supabase_client: SupabaseManagementClient,
    ) -> None:
        self._settings = settings
        self._cipher = cipher
        self._supabase = supabase_client

    async def start_supabase_authorization(
        self,
        *,
        principal: Principal,
        repository: ConnectionRepository,
        organization_slug: str | None,
    ) -> AuthorizationStartResponse:
        material = create_oauth_material()
        expires_at = datetime.now(UTC) + timedelta(
            seconds=self._settings.oauth_transaction_ttl_seconds
        )
        await repository.create_oauth_transaction(
            owner_subject=principal.subject,
            tenant_id=principal.tenant_id,
            provider="supabase",
            state_digest=material.state_digest,
            encrypted_context=self._cipher.encrypt({"code_verifier": material.code_verifier}),
            expires_at=expires_at,
        )
        return AuthorizationStartResponse(
            authorization_url=self._supabase.authorization_url(
                state=material.state,
                code_challenge=material.code_challenge,
                organization_slug=organization_slug,
            ),
            expires_at=expires_at,
        )

    async def complete_supabase_authorization(
        self,
        *,
        repository: ConnectionRepository,
        code: str | None,
        state: str | None,
        provider_error: str | None,
    ) -> OAuthCallbackResponse:
        if provider_error or not code or not state:
            raise InvalidRequestError("Supabase authorization was not completed.")
        transaction = await repository.consume_oauth_transaction(
            provider="supabase",
            state_digest=digest_oauth_state(state),
        )
        context = self._cipher.decrypt(transaction.encrypted_context)
        code_verifier = context.get("code_verifier")
        if not isinstance(code_verifier, str) or not code_verifier:
            raise InvalidRequestError("The stored OAuth transaction is invalid.")
        tokens = await self._supabase.exchange_code(
            code=code,
            code_verifier=code_verifier,
        )
        connection = await repository.create_connection(
            owner_subject=transaction.owner_subject,
            tenant_id=transaction.tenant_id,
            provider="supabase",
            encrypted_credentials=self._cipher.encrypt(tokens.secret_document()),
            token_expires_at=tokens.expires_at,
        )
        return OAuthCallbackResponse(
            connection=self.response(connection),
            next_step="List the authorized projects, then select one for this connection.",
        )

    async def access_token(
        self,
        *,
        connection: ProviderConnection,
        repository: ConnectionRepository,
    ) -> str:
        tokens = OAuthTokens.from_secret(self._cipher.decrypt(connection.encrypted_credentials))
        refresh_at = datetime.now(UTC) + timedelta(
            seconds=self._settings.supabase_oauth_token_skew_seconds
        )
        expires_at = tokens.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= refresh_at:
            tokens = await self._supabase.refresh_tokens(tokens.refresh_token)
            connection.encrypted_credentials = self._cipher.encrypt(tokens.secret_document())
            connection.token_expires_at = tokens.expires_at
            await repository.save(connection)
        return tokens.access_token

    async def disconnect_supabase(
        self,
        *,
        connection: ProviderConnection,
        repository: ConnectionRepository,
    ) -> None:
        tokens = OAuthTokens.from_secret(self._cipher.decrypt(connection.encrypted_credentials))
        await self._supabase.revoke(tokens.refresh_token)
        connection.encrypted_credentials = self._cipher.encrypt({"revoked": True})
        await repository.disconnect(connection)

    @staticmethod
    def response(connection: ProviderConnection) -> ConnectionResponse:
        return ConnectionResponse(
            id=connection.id,
            provider=connection.provider,
            status=connection.status,
            external_reference=connection.external_reference,
            display_name=connection.display_name,
            scopes=connection.scopes,
            created_at=connection.created_at,
        )
