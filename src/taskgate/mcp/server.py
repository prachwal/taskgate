"""MCP stdio server for the task registry (stdlib-only)."""

from __future__ import annotations

from typing import Any

from .. import __version__
from . import protocol, registry, tools  # noqa: F401  (importing tools registers them)

SERVER_INFO = {"name": "taskgate", "version": __version__}


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    """JSON-RPC dispatcher bound to this server's tools. Returns None for notifications."""
    return protocol.handle_request(request, tools=registry.TOOLS, server_info=SERVER_INFO)


def serve() -> None:
    """Run the stdio loop until EOF."""
    protocol.serve(tools=registry.TOOLS, server_info=SERVER_INFO)


def run() -> None:
    """Console-script entry point (``taskgate-mcp``)."""
    serve()
