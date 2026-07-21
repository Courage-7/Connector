"""Owner-scoped persistence operations for provider connections."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from connector_service.core.exceptions import InvalidRequestError, NotFoundError
from connector_service.infrastructure.database.models import (
    OAuthTransaction,
    ProviderConnection,
)


class ConnectionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create_oauth_transaction(
        self,
        *,
        owner_subject: str,
        tenant_id: str,
        provider: str,
        state_digest: bytes,
        encrypted_context: bytes,
        expires_at: datetime,
    ) -> OAuthTransaction:
        transaction = OAuthTransaction(
            owner_subject=owner_subject,
            tenant_id=tenant_id,
            provider=provider,
            state_digest=state_digest,
            encrypted_context=encrypted_context,
            expires_at=expires_at,
        )
        self._session.add(transaction)
        await self._session.commit()
        await self._session.refresh(transaction)
        return transaction

    async def consume_oauth_transaction(
        self,
        *,
        provider: str,
        state_digest: bytes,
    ) -> OAuthTransaction:
        now = datetime.now(UTC)
        transaction = await self._session.scalar(
            select(OAuthTransaction)
            .where(
                OAuthTransaction.provider == provider,
                OAuthTransaction.state_digest == state_digest,
                OAuthTransaction.consumed_at.is_(None),
                OAuthTransaction.expires_at > now,
            )
            .with_for_update()
        )
        if transaction is None:
            raise InvalidRequestError("The OAuth state is invalid, expired, or already used.")
        transaction.consumed_at = now
        await self._session.commit()
        return transaction

    async def create_connection(
        self,
        *,
        owner_subject: str,
        tenant_id: str,
        provider: str,
        encrypted_credentials: bytes,
        token_expires_at: datetime,
        scopes: list[str] | None = None,
    ) -> ProviderConnection:
        connection = ProviderConnection(
            owner_subject=owner_subject,
            tenant_id=tenant_id,
            provider=provider,
            status="pending_resource",
            encrypted_credentials=encrypted_credentials,
            token_expires_at=token_expires_at,
            scopes=scopes or [],
        )
        self._session.add(connection)
        await self._session.commit()
        await self._session.refresh(connection)
        return connection

    async def list_connections(self, *, owner_subject: str) -> list[ProviderConnection]:
        return list(
            await self._session.scalars(
                select(ProviderConnection)
                .where(
                    ProviderConnection.owner_subject == owner_subject,
                    ProviderConnection.status != "disconnected",
                )
                .order_by(ProviderConnection.created_at.desc())
            )
        )

    async def get_connection(
        self,
        *,
        connection_id: str,
        owner_subject: str,
        provider: str | None = None,
    ) -> ProviderConnection:
        predicates = [
            ProviderConnection.id == connection_id,
            ProviderConnection.owner_subject == owner_subject,
            ProviderConnection.status != "disconnected",
        ]
        if provider is not None:
            predicates.append(ProviderConnection.provider == provider)
        connection = await self._session.scalar(select(ProviderConnection).where(*predicates))
        if connection is None:
            raise NotFoundError("The requested provider connection was not found.")
        return connection

    async def save(self, connection: ProviderConnection) -> ProviderConnection:
        await self._session.commit()
        await self._session.refresh(connection)
        return connection

    async def disconnect(self, connection: ProviderConnection) -> None:
        connection.status = "disconnected"
        connection.disconnected_at = datetime.now(UTC)
        await self._session.commit()
