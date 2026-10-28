"""Tool table, decorator and argument helper."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

Handler = Callable[[dict[str, Any]], str]
ToolSpec = dict[str, Any]


class Registry:
    """A tool table: name -> spec (``name``, ``description``, ``inputSchema``, ``handler``)."""

    def __init__(self) -> None:
        self.tools: dict[str, ToolSpec] = {}

    def tool(
        self, name: str, description: str, input_schema: dict[str, Any], *, read_only: bool = False
    ) -> Callable[[Handler], Handler]:
        """Decorator registering a handler. ``read_only`` lets clients skip the approval prompt."""

        def decorator(func: Handler) -> Handler:
            spec: ToolSpec = {
                "name": name,
                "description": description,
                "inputSchema": {"type": "object", **input_schema},
                "annotations": {"readOnlyHint": read_only},
                "handler": func,
            }
            self.tools[name] = spec
            return func

        return decorator


REGISTRY = Registry()
TOOLS = REGISTRY.tools
tool = REGISTRY.tool


def arg(value: dict[str, Any], key: str, default: Any = None) -> Any:
    """Read ``key`` from a tool's arguments with an optional default."""
    return value.get(key, default)
