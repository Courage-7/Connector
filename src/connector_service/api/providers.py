"""Provider discovery for consuming projects and dashboards."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request

from connector_service.api.dependencies import require_project
from connector_service.core.contracts import StrictModel
from connector_service.db.models import Project
from connector_service.providers.catalog import ProviderCatalog

router = APIRouter(prefix="/v1/providers", tags=["providers"])


class ProviderResponse(StrictModel):
    name: str
    display_name: str
    configured: bool
    capabilities: list[str]


@router.get("", response_model=list[ProviderResponse])
def list_providers(
    request: Request,
    _project: Annotated[Project, Depends(require_project)],
) -> list[ProviderResponse]:
    catalog: ProviderCatalog = request.app.state.providers
    return [
        ProviderResponse(
            name=module.name,
            display_name=module.display_name,
            configured=module.configured,
            capabilities=sorted(module.capabilities),
        )
        for module in catalog.modules()
    ]
