"""Ready-to-paste MCP server configuration for common clients (``taskgate config-snippet``)."""

from __future__ import annotations

import json

CLIENTS = {
    "claude": "Claude Code: .mcp.json in the project (or `claude mcp add`)",
    "vscode": "VS Code (GitHub Copilot agent mode): .vscode/mcp.json",
    "codex": "OpenAI Codex CLI: ~/.codex/config.toml",
    "cursor": "Cursor: .cursor/mcp.json",
    "gemini": "Gemini CLI: .gemini/settings.json",
    "generic": "any client that takes a command and arguments",
}


def launch(source: str | None) -> tuple[str, list[str]]:
    """Command and arguments that start the stdio server through ``uvx``."""
    args = ["--from", source, "taskgate", "mcp"] if source else ["taskgate", "mcp"]
    return "uvx", args


def snippet(client: str, *, source: str | None = None, root: str | None = None) -> str:
    """The configuration text for ``client``; raises ``ValueError`` for an unknown client."""
    if client not in CLIENTS:
        raise ValueError(f"unknown client {client!r}; choose one of {', '.join(CLIENTS)}")
    command, args = launch(source)
    env = {"TASKGATE_ROOT": root} if root else {}
    if client == "codex":
        lines = ["[mcp_servers.taskgate]", f"command = {json.dumps(command)}", f"args = {json.dumps(args)}"]
        if env:
            lines += ["", "[mcp_servers.taskgate.env]", f"TASKGATE_ROOT = {json.dumps(root)}"]
        return "\n".join(lines) + "\n"
    if client == "claude":
        add = ["claude", "mcp", "add", "taskgate"]
        if root:
            add += ["-e", f"TASKGATE_ROOT={root}"]
        add += ["--", command, *args]
        entry: dict[str, object] = {"type": "stdio", "command": command, "args": args}
        if env:
            entry["env"] = env
        text = json.dumps({"mcpServers": {"taskgate": entry}}, indent=2)
        return f"# one command:\n{' '.join(add)}\n\n# or .mcp.json:\n{text}\n"
    if client == "vscode":
        entry = {"type": "stdio", "command": command, "args": args}
        if env:
            entry["env"] = env
        return json.dumps({"servers": {"taskgate": entry}}, indent=2) + "\n"
    entry = {"command": command, "args": args}
    if env:
        entry["env"] = env
    return json.dumps({"mcpServers": {"taskgate": entry}}, indent=2) + "\n"
