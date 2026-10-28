from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from conftest import Run, add

from taskgate.mcp import protocol, server
from taskgate.mcp.registry import TOOLS


def call(method: str, params: dict[str, Any] | None = None, request_id: int | None = 1) -> dict[str, Any] | None:
    request: dict[str, Any] = {"jsonrpc": "2.0", "method": method, "params": params or {}}
    if request_id is not None:
        request["id"] = request_id
    return server.handle_request(request)


def text_of(response: dict[str, Any] | None) -> tuple[str, bool]:
    assert response is not None
    result = response["result"]
    return result["content"][0]["text"], result["isError"]


def test_initialize_echoes_protocol_version() -> None:
    response = call("initialize", {"protocolVersion": "2024-11-05"})
    assert response is not None
    assert response["result"]["protocolVersion"] == "2024-11-05"
    assert response["result"]["serverInfo"]["name"] == "taskgate"
    assert response["result"]["capabilities"] == {"tools": {}}


def test_notifications_get_no_reply() -> None:
    assert call("notifications/initialized", request_id=None) is None


def test_tools_list_hides_handlers_and_marks_read_only() -> None:
    response = call("tools/list")
    assert response is not None
    tools = {t["name"]: t for t in response["result"]["tools"]}
    assert set(tools) == set(TOOLS)
    assert all("handler" not in t for t in tools.values())
    assert tools["task_list"]["annotations"]["readOnlyHint"] is True
    assert tools["task_claim"]["annotations"]["readOnlyHint"] is False
    assert all(t["inputSchema"]["type"] == "object" for t in tools.values())


def test_unknown_tool_and_method() -> None:
    response = call("tools/call", {"name": "nope"})
    assert response is not None and response["error"]["code"] == -32601
    response = call("resources/list")
    assert response is not None and response["error"]["code"] == -32601


def test_tool_roundtrip(tg: Run, project: Path) -> None:
    tg("init")
    add(tg, "T-1")
    text, is_error = text_of(call("tools/call", {"name": "task_list", "arguments": {}}))
    assert not is_error and "T-1" in text
    text, is_error = text_of(call("tools/call", {"name": "task_claim", "arguments": {"id": "T-1", "by": "dev"}}))
    assert not is_error and "in_progress" in text


def test_tool_errors_ride_in_the_envelope(tg: Run) -> None:
    tg("init")
    text, is_error = text_of(call("tools/call", {"name": "task_claim", "arguments": {"id": "T-404"}}))
    assert is_error and "unknown task" in text


def test_task_move_requires_exactly_one_anchor(tg: Run) -> None:
    tg("init")
    text, is_error = text_of(call("tools/call", {"name": "task_move", "arguments": {"id": "T-1", "by": "human"}}))
    assert is_error and "exactly one" in text


def test_missing_project_is_an_error_not_a_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TASKGATE_ROOT", raising=False)
    text, is_error = text_of(call("tools/call", {"name": "task_list", "arguments": {}}))
    assert is_error and "no taskgate project" in text


def test_quality_check(project: Path, tg: Run) -> None:
    (project / "taskgate.toml").write_text(
        "review_delay_seconds = 0\n[quality]\n"
        'ok = [["python3", "-c", "print(1)"]]\n'
        'fail = [["python3", "-c", "raise SystemExit(3)"]]\n',
        encoding="utf-8",
    )
    tg("init")
    text, is_error = text_of(call("tools/call", {"name": "quality_check", "arguments": {"checks": ["ok", "tasks"]}}))
    report = json.loads(text)
    assert not is_error and report["ok"] and {r["check"] for r in report["results"]} == {"ok", "tasks"}
    text, is_error = text_of(call("tools/call", {"name": "quality_check", "arguments": {"checks": ["fail"]}}))
    assert is_error and json.loads(text)["results"][0]["exit"] == 3
    text, is_error = text_of(call("tools/call", {"name": "quality_check", "arguments": {"checks": ["zzz"]}}))
    assert is_error and "unknown quality checks" in text


def test_stdio_loop_survives_garbage(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    lines = "not json\n\n" + json.dumps({"jsonrpc": "2.0", "id": 7, "method": "ping"}) + "\n"
    monkeypatch.setattr("sys.stdin", io.StringIO(lines))
    protocol.serve(tools=TOOLS, server_info=server.SERVER_INFO)
    replies = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert replies[0]["error"]["code"] == -32700
    assert replies[1] == {"jsonrpc": "2.0", "id": 7, "result": {}}
