"""FastAPI dependencies backed by the composition root."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from connector_service.connections.repository import ConnectionRepository
from connector_service.identity.api import require_principal
from connector_service.identity.principal import Principal


async def get_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.database.session_factory() as session:
        yield session


async def get_connection_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ConnectionRepository:
    return ConnectionRepository(session)


AuthenticatedPrincipal = Annotated[Principal, Depends(require_principal)]
RepositoryDependency = Annotated[
    ConnectionRepository,
    Depends(get_connection_repository),
]
