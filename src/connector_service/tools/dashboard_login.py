"""Open a one-time, cookie-authenticated dashboard session."""

from __future__ import annotations

import argparse
import sys
import webbrowser

import httpx

from connector_service.mcp_server import MCPSettings


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Open Connector without exposing the tenant API key to browser code."
    )
    parser.add_argument(
        "--no-open",
        action="store_true",
        help="Print the one-time URL instead of opening the default browser.",
    )
    arguments = parser.parse_args()
    settings = MCPSettings()  # type: ignore[call-arg]
    try:
        with httpx.Client(
            base_url=settings.base_url,
            headers={"X-API-Key": settings.api_key.get_secret_value()},
            timeout=settings.timeout_seconds,
            trust_env=False,
        ) as client:
            response = client.post(
                "/v1/dashboard/login-tickets",
                json={"return_to": "/app/"},
            )
        response.raise_for_status()
        login_url = response.json()["login_url"]
    except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
        print("Could not create a dashboard login ticket.", file=sys.stderr)
        raise SystemExit(1) from exc

    if arguments.no_open:
        print(login_url)
        return
    if not webbrowser.open(login_url, new=2):
        print(login_url)


if __name__ == "__main__":
    main()
