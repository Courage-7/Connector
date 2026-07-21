"""Authenticated caller identity shared by REST and MCP adapters."""

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Principal:
    subject: str
    tenant_id: str
    authentication_method: str
