"""JSON-RPC 2.0 dispatcher and stdio loop (MCP stdio transport, newline-delimited).

Everything written to stdout is protocol; tool output is captured into the
content envelope, so handler print chatter never touches the stream.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from . import registry

DEFAULT_PROTOCOL_VERSION = "2025-06-18"


def _ok(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def handle_request(
    request: dict[str, Any],
    *,
    tools: dict[str, registry.ToolSpec],
    server_info: dict[str, str],
) -> dict[str, Any] | None:
    """Pure JSON-RPC dispatcher. Returns None for notifications."""
    method = request.get("method", "")
    request_id = request.get("id")
    if method.startswith("notifications/") or request_id is None:
        return None
    if method == "initialize":
        params = request.get("params") or {}
        return _ok(request_id, {
            "protocolVersion": params.get("protocolVersion", DEFAULT_PROTOCOL_VERSION),
            "capabilities": {"tools": {}},
            "serverInfo": server_info,
        })
    if method == "ping":
        return _ok(request_id, {})
    if method == "tools/list":
        return _ok(request_id, {"tools": [{k: v for k, v in spec.items() if k != "handler"} for spec in tools.values()]})
    if method == "tools/call":
        params = request.get("params") or {}
        name = str(params.get("name", ""))
        spec = tools.get(name)
        if spec is None:
            return _error(request_id, -32601, f"unknown tool {name!r}")
        try:
            text = spec["handler"](params.get("arguments") or {})
        except (Exception, SystemExit) as exc:  # tool errors ride in the envelope
            return _ok(request_id, {"content": [{"type": "text", "text": str(exc)}], "isError": True})
        return _ok(request_id, {"content": [{"type": "text", "text": text}], "isError": False})
    return _error(request_id, -32601, f"method not found: {method}")


def serve(*, tools: dict[str, registry.ToolSpec], server_info: dict[str, str]) -> None:
    """Run the stdio loop until EOF, answering each line on stdout."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except json.JSONDecodeError:
            response: dict[str, Any] | None = _error(None, -32700, "parse error")
        else:
            response = handle_request(request, tools=tools, server_info=server_info)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
