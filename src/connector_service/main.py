"""ASGI entry point."""

from connector_service.bootstrap.app import create_app

app = create_app()
