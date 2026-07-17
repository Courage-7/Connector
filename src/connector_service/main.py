"""ASGI entry point."""

from connector_service.app import create_app

app = create_app()
