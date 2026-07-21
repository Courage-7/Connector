"""Provider manifest contracts returned to applications and agents."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from connector_service.core.contracts import StrictModel


class ToolManifest(StrictModel):
    name: str
    display_name: str
    description: str
    capability: str
    operation_type: Literal["read", "write"]
    implemented: bool
    input_schema: dict[str, Any] = Field(default_factory=dict)


class ProviderManifest(StrictModel):
    name: str
    display_name: str
    status: Literal["available", "planned"]
    configured: bool
    capabilities: list[str]
    tools: list[ToolManifest]
