"""Connector registry and execution protocol."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from connector_service.core.contracts import ActionExecutionResponse
from connector_service.core.exceptions import NotFoundError


@dataclass(frozen=True, slots=True)
class ActionContext:
    project_id: str
    grant_id: str


class Connector(Protocol):
    name: str
    actions: frozenset[str]

    async def execute(
        self,
        action: str,
        *,
        context: ActionContext,
        credential: dict[str, Any],
        policy: dict[str, Any],
        payload: dict[str, Any],
    ) -> ActionExecutionResponse: ...


class ConnectorRegistry:
    """Explicit registry; importing a module never exposes an action automatically."""

    def __init__(self) -> None:
        self._connectors: dict[str, Connector] = {}

    def register(self, connector: Connector, *, replace: bool = False) -> None:
        if connector.name in self._connectors and not replace:
            raise ValueError(f"connector already registered: {connector.name}")
        self._connectors[connector.name] = connector

    def get(self, name: str) -> Connector:
        connector = self._connectors.get(name)
        if connector is None:
            raise NotFoundError("The requested connector is not registered.")
        return connector

    def supports(self, connector: str, action: str) -> bool:
        registered = self._connectors.get(connector)
        return registered is not None and action in registered.actions

    def catalog(self) -> dict[str, list[str]]:
        return {
            name: sorted(connector.actions) for name, connector in sorted(self._connectors.items())
        }
