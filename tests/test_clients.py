from __future__ import annotations

import json
import tomllib

import pytest

from taskgate import cli, clients


@pytest.mark.parametrize("client", ["vscode", "cursor", "gemini", "generic"])
def test_json_snippets_are_valid(client: str) -> None:
    data = json.loads(clients.snippet(client))
    key = "servers" if client == "vscode" else "mcpServers"
    entry = data[key]["taskgate"]
    assert entry["command"] == "uvx" and entry["args"] == ["taskgate", "mcp"]
    assert (entry.get("type") == "stdio") == (client == "vscode")


def test_codex_snippet_is_valid_toml_with_env() -> None:
    data = tomllib.loads(clients.snippet("codex", source="/src/taskgate", root="/work/p"))
    server = data["mcp_servers"]["taskgate"]
    assert server["args"] == ["--from", "/src/taskgate", "taskgate", "mcp"]
    assert server["env"] == {"TASKGATE_ROOT": "/work/p"}


def test_claude_snippet_has_command_and_json() -> None:
    text = clients.snippet("claude", root="/work/p")
    assert "claude mcp add taskgate -e TASKGATE_ROOT=/work/p -- uvx taskgate mcp" in text
    assert json.loads(text[text.index("{"):])["mcpServers"]["taskgate"]["env"] == {"TASKGATE_ROOT": "/work/p"}


def test_unknown_client() -> None:
    with pytest.raises(ValueError, match="unknown client"):
        clients.snippet("emacs")


def test_cli_prints_snippet(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["config-snippet", "vscode"]) == 0
    assert '"servers"' in capsys.readouterr().out


def test_package_version_matches_pyproject() -> None:
    import tomllib
    from pathlib import Path

    import taskgate

    pyproject = Path(__file__).resolve().parent.parent / "pyproject.toml"
    assert tomllib.loads(pyproject.read_text(encoding="utf-8"))["project"]["version"] == taskgate.__version__
