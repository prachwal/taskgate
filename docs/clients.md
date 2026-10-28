# Adding taskgate to an MCP client

Every client runs the same stdio command: `uvx taskgate mcp`. `taskgate config-snippet <client>` prints the
block for you; `--from <path|git-url>` points `uvx` at a checkout instead of PyPI, and `--root <dir>` pins the
project (written as `TASKGATE_ROOT`).

The server finds the project from its working directory (nearest `taskgate.toml` or `.taskgate/`). Claude Code
and VS Code start servers in the workspace, so nothing more is needed there. Clients that start servers
elsewhere (Claude Desktop, some Codex setups) need `--root`.

| Client | Where it goes | Command |
| --- | --- | --- |
| Claude Code | `.mcp.json` in the project, or `claude mcp add` | `taskgate config-snippet claude` |
| VS Code (GitHub Copilot agent mode) | `.vscode/mcp.json` | `taskgate config-snippet vscode` |
| OpenAI Codex CLI | `~/.codex/config.toml` | `taskgate config-snippet codex` |
| Cursor | `.cursor/mcp.json` | `taskgate config-snippet cursor` |
| Gemini CLI | `.gemini/settings.json` | `taskgate config-snippet gemini` |
| anything else | the client's MCP settings | `taskgate config-snippet generic` |

## Examples

Claude Code:

```sh
claude mcp add taskgate -- uvx taskgate mcp
```

VS Code `.vscode/mcp.json`:

```json
{
  "servers": {
    "taskgate": { "type": "stdio", "command": "uvx", "args": ["taskgate", "mcp"] }
  }
}
```

Codex `~/.codex/config.toml`:

```toml
[mcp_servers.taskgate]
command = "uvx"
args = ["taskgate", "mcp"]

[mcp_servers.taskgate.env]
TASKGATE_ROOT = "/absolute/path/to/project"
```

## Notes

- The file formats above are the ones the clients documented when this was written; client configuration
  changes between releases, so check the client's current MCP documentation if a block is rejected.
- `uvx` must be on the `PATH` the client sees. Use an absolute path to `uvx` (`command -v uvx`) if it is not.
- Agents pass their role with the `by` argument. Give the implementing agent and the reviewing agent different
  identities, and keep planner identities (`planners` in `taskgate.toml`) for the agent that plans work.
