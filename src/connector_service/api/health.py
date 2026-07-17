"""Operational health routes."""

from fastapi import APIRouter

from connector_service import __version__

router = APIRouter(tags=["operations"])


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}
