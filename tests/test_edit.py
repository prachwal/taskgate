from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from conftest import GREEN, Run, add, task_of

from taskgate.mcp import server


def tool(name: str, arguments: dict[str, Any]) -> tuple[str, bool]:
    response = server.handle_request(
        {"jsonrpc": "2.0", "id": 1, "method": "tools/call", "params": {"name": name, "arguments": arguments}}
    )
    assert response is not None
    result = response["result"]
    return result["content"][0]["text"], result["isError"]


def test_edit_changes_title_spec_and_command(tg: Run, project: Path) -> None:
    tg("init")
    add(tg, "T-1")
    code, out, err = tg("edit", "T-1", "--title", "new", "--spec", "docs/x.md#2", "--verification-cmd", "make", "--by", "human")
    assert code == 0, err
    task = task_of(project, "T-1")
    assert (task["title"], task["spec_source"], task["verification_cmd"]) == ("new", "docs/x.md#2", "make")
    assert tg("edit", "T-1", "--spec", "", "--by", "human")[0] == 0
    assert "spec_source" not in task_of(project, "T-1")
    assert "edit" in tg("log", "--task", "T-1")[1]


def test_edit_is_for_planners_and_unstarted_tasks(tg: Run) -> None:
    tg("init")
    add(tg, "T-1")
    code, _, err = tg("edit", "T-1", "--title", "x", "--by", "dev")
    assert code == 1 and "may edit" in err
    assert tg("edit", "T-1", "--by", "human")[0] == 1
    assert tg("edit", "T-404", "--title", "x", "--by", "human")[0] == 1
    tg("claim", "T-1", "--by", "dev")
    code, _, err = tg("edit", "T-1", "--title", "x", "--by", "human")
    assert code == 1 and "only draft/planned" in err


def test_note_works_in_any_status_and_rejects_blank(tg: Run, project: Path) -> None:
    tg("init")
    add(tg, "T-1")
    tg("claim", "T-1", "--by", "dev")
    assert tg("note", "T-1", "found a gap", "--by", "dev")[0] == 0
    assert task_of(project, "T-1")["notes"][0]["text"] == "found a gap"  # type: ignore[index]
    assert tg("note", "T-1", "  ")[0] == 1
    assert tg("note", "T-404", "x")[0] == 1


def test_update_without_effect_is_an_error(tg: Run) -> None:
    tg("init")
    add(tg, "T-1")
    code, _, err = tg("update", "T-1", "--by", "dev")
    assert code == 1 and "nothing to update" in err


def test_returning_from_review_records_the_reason(tg: Run, project: Path) -> None:
    tg("init")
    add(tg, "T-1")
    tg("claim", "T-1", "--by", "dev")
    tg("update", "T-1", "--verification-result", GREEN, "--status", "in_review", "--by", "dev")
    code, _, err = tg("update", "T-1", "--status", "in_progress", "--reason", "tests missing", "--by", "reviewer")
    assert code == 0, err
    assert "returned from review: tests missing" in json.dumps(task_of(project, "T-1")["notes"])


def test_log_filters_and_prints_json(tg: Run) -> None:
    tg("init")
    add(tg, "T-1")
    add(tg, "T-2")
    tg("claim", "T-1", "--by", "dev")
    _, out, _ = tg("log", "--task", "T-1")
    assert "T-1" in out and "T-2" not in out
    events = json.loads(tg("log", "--json", "--by", "dev")[1])
    assert [e["op"] for e in events] == ["claim"]
    assert "1 event" in tg("log", "--limit", "1")[1]


def test_list_and_next_json(tg: Run) -> None:
    tg("init")
    add(tg, "T-1")
    rows = json.loads(tg("list", "--json", "--status", "planned")[1])
    assert [r["id"] for r in rows] == ["T-1"]
    assert json.loads(tg("next", "--json")[1])["id"] == "T-1"


def test_doctor_reports_setup(tg: Run, project: Path) -> None:
    code, out, _ = tg("doctor")
    assert code == 1 and "not found" in out
    tg("init")
    code, out, _ = tg("doctor")
    assert code == 0 and "registry valid" in out and "view in sync" in out
    (project / ".taskgate" / "tasks.md").write_text("stale", encoding="utf-8")
    code, out, _ = tg("doctor")
    assert code == 1 and "drifted" in out


def test_mcp_rejects_unknown_and_missing_arguments(tg: Run) -> None:
    tg("init")
    add(tg, "T-1")
    text, is_error = tool("task_add", {"id": "T-2", "title": "t", "verification_cmd": "x", "by": "human", "spec_source": "d"})
    assert is_error and "unknown argument" in text and "spec_source" in text
    text, is_error = tool("task_claim", {"by": "dev"})
    assert is_error and "missing required" in text


def test_mcp_edit_note_log_and_doctor(tg: Run, project: Path) -> None:
    tg("init")
    add(tg, "T-1")
    assert not tool("task_edit", {"id": "T-1", "by": "human", "spec": "docs/a.md"})[1]
    assert task_of(project, "T-1")["spec_source"] == "docs/a.md"
    assert not tool("task_note", {"id": "T-1", "text": "hello", "by": "dev"})[1]
    events = json.loads(tool("task_log", {"task": "T-1", "limit": 5})[0])
    assert {e["op"] for e in events} >= {"add", "edit", "note"}
    assert "registry valid" in tool("task_doctor", {})[0]
    assert json.loads(tool("task_list", {"json": True})[0])[0]["id"] == "T-1"
