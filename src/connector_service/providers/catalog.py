"""Typed catalog for independently reusable provider modules."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType
from typing import Any, TypeVar, cast

from connector_service.connectors.email.base import EmailClient
from connector_service.core.exceptions import NotFoundError
from connector_service.core.registry import Connector


class ProviderCapability(StrEnum):
    """Provider-neutral features used to compose routes and agent surfaces."""

    ACTIONS = "actions"
    DATABASE = "database"
    EMAIL = "email"
    EMAIL_SEND = "email.send"
    OAUTH = "oauth"


@dataclass(frozen=True, slots=True)
class ProviderModule:
    """One provider's runtime services and declared capabilities."""

    name: str
    display_name: str
    capabilities: frozenset[ProviderCapability]
    configured: bool
    connectors: tuple[Connector, ...] = ()
    email_client: EmailClient | None = None
    services: Mapping[type[Any], object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        normalized = self.name.strip().lower()
        if not normalized or normalized != self.name:
            raise ValueError("provider module names must be normalized lowercase slugs")
        object.__setattr__(self, "services", MappingProxyType(dict(self.services)))


T = TypeVar("T")


class ProviderCatalog:
    """Explicit provider registry; disabled modules are never constructed."""

    def __init__(self, modules: list[ProviderModule] | tuple[ProviderModule, ...]) -> None:
        self._modules: dict[str, ProviderModule] = {}
        for module in modules:
            if module.name in self._modules:
                raise ValueError(f"provider module already registered: {module.name}")
            self._modules[module.name] = module

    @property
    def enabled_names(self) -> frozenset[str]:
        return frozenset(self._modules)

    def modules(self) -> tuple[ProviderModule, ...]:
        return tuple(self._modules[name] for name in sorted(self._modules))

    def get(self, name: str) -> ProviderModule:
        module = self._modules.get(name)
        if module is None:
            raise NotFoundError("The requested provider is not enabled for this deployment.")
        return module

    def has_capability(self, capability: ProviderCapability) -> bool:
        return any(capability in module.capabilities for module in self._modules.values())

    def email_client(self, name: str) -> EmailClient:
        client = self.get(name).email_client
        if client is None:
            raise NotFoundError("The requested provider does not expose mailbox tools.")
        return client

    def require_service(self, name: str, service_type: type[T]) -> T:
        service = self.get(name).services.get(service_type)
        if service is None:
            raise NotFoundError("The requested provider service is not enabled.")
        return cast(T, service)

    def connectors(self) -> tuple[Connector, ...]:
        return tuple(connector for module in self.modules() for connector in module.connectors)
