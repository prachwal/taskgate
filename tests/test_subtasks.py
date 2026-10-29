from __future__ import annotations

import json
from pathlib import Path

import pytest
from conftest import GREEN, REVIEW, Run, add, registry, task_of
from test_mcp import call, text_of

from taskgate import cli, config
from taskgate.model import validate

PROFILES = """
review_delay_seconds = 0

[quality]
build = [["python3", "-c", "print('build')"]]
docs = [["python3", "-c", "print('docs')"]]

[profiles.docs]
require_review = false
gates = ["docs", "tasks"]

[profiles.light]
reviewer = "reviewer-lite"
gates = ["docs"]
"""

LITE = '{"ok": true, "by": "reviewer-lite", "checks": ["cmd"]}'


@pytest.fixture
def pj(project: Path, tg: Run) -> Run:
    """A project with profiles, initialised."""
    (project / "taskgate.toml").write_text(PROFILES, encoding="utf-8")
    assert tg("init")[0] == 0
    return tg


def test_profile_without_review_closes_on_verification(pj: Run, project: Path) -> None:
    add(pj, "T-1", "--profile", "docs")
    add(pj, "T-2")
    assert pj("claim", "T-1", "--by", "dev")[0] == 0
    assert pj("update", "T-1", "--verification-result", GREEN, "--by", "dev")[0] == 0
    assert pj("update", "T-1", "--status", "in_review", "--by", "dev")[0] == 0
    code, _, err = pj("update", "T-1", "--status", "done", "--by", "dev")
    assert code == 0, err
    # the project-wide default still demands a review
    pj("claim", "T-2", "--by", "dev")
    pj("update", "T-2", "--verification-result", GREEN, "--status", "in_review", "--by", "dev")
    assert pj("update", "T-2", "--status", "done", "--by", "dev")[0] == 1


def test_profile_reviewer_replaces_the_default_reviewer(pj: Run, project: Path) -> None:
    add(pj, "T-1", "--profile", "light")
    pj("claim", "T-1", "--by", "dev")
    pj("update", "T-1", "--verification-result", GREEN, "--status", "in_review", "--by", "dev")
    code, _, err = pj("update", "T-1", "--review-result", REVIEW, "--by", "reviewer")
    assert code == 1 and "reviewer-lite" in err
    assert pj("update", "T-1", "--review-result", LITE, "--by", "reviewer-lite")[0] == 0
    assert pj("update", "T-1", "--status", "done", "--review-result", LITE, "--by", "reviewer-lite")[0] == 0
    assert task_of(project, "T-1")["status"] == "done"


def test_unknown_profile_is_refused(pj: Run) -> None:
    code, _, err = pj("add", "--id", "T-1", "--title", "t", "--verification-cmd", "true", "--profile", "nope", "--by", "human")
    assert code == 1 and "unknown profile" in err


def test_profile_command_is_planner_only_and_locked_after_start(pj: Run, project: Path) -> None:
    add(pj, "T-1")
    assert pj("profile", "T-1", "docs", "--by", "dev")[0] == 1
    assert pj("profile", "T-1", "docs", "--by", "human")[0] == 0
    assert task_of(project, "T-1")["profile"] == "docs"
    assert pj("profile", "T-1", "--clear", "--by", "human")[0] == 0
    assert "profile" not in task_of(project, "T-1")
    assert pj("profile", "T-1", "--by", "human")[0] == 1
    pj("claim", "T-1", "--by", "dev")
    code, _, err = pj("profile", "T-1", "docs", "--by", "human")
    assert code == 1 and "draft or planned" in err


def test_subtask_ids_position_and_inheritance(pj: Run, project: Path) -> None:
    add(pj, "T-1", "--profile", "docs")
    add(pj, "T-2")
    for _ in range(2):
        code, out, err = pj("add", "--parent", "T-1", "--title", "step", "--verification-cmd", "true", "--by", "human")
        assert code == 0, err
    ids = [t["id"] for t in registry(project)["tasks"]]  # type: ignore[union-attr]
    assert ids == ["T-1", "T-1.1", "T-1.2", "T-2"]
    child = task_of(project, "T-1.1")
    assert child["parent"] == "T-1" and child["phase"] == 0 and "profile" not in child
    code, out, _ = pj("show", "T-1.1")
    shown = json.loads(out)
    assert shown["policy"]["profile"] == "docs" and shown["policy"]["require_review"] is False
    assert [c["id"] for c in json.loads(pj("show", "T-1")[1])["subtasks"]] == ["T-1.1", "T-1.2"]


def test_subtasks_start_only_under_a_started_parent(pj: Run) -> None:
    add(pj, "T-1")
    pj("add", "--parent", "T-1", "--title", "a", "--verification-cmd", "true", "--by", "human")
    code, _, err = pj("claim", "T-1.1", "--by", "dev")
    assert code == 1 and "claim the parent first" in err
    assert pj("claim", "T-1", "--by", "dev")[0] == 0
    code, out, _ = pj("next")
    assert code == 0 and out.startswith("T-1.1 ")
    assert pj("claim", "T-1.1", "--by", "dev")[0] == 0


def test_parent_cannot_close_over_open_subtasks(pj: Run) -> None:
    add(pj, "T-1")
    pj("add", "--parent", "T-1", "--title", "a", "--verification-cmd", "true", "--by", "human")
    pj("claim", "T-1", "--by", "dev")
    pj("update", "T-1", "--verification-result", GREEN, "--by", "dev")
    for status in ("in_review", "cancelled"):
        code, _, err = pj("update", "T-1", "--status", status, "--by", "dev")
        assert code == 1 and "subtasks are open" in err
    pj("claim", "T-1.1", "--by", "dev")
    pj("update", "T-1.1", "--verification-result", GREEN, "--status", "in_review", "--by", "dev")
    assert pj("update", "T-1.1", "--status", "done", "--review-result", REVIEW, "--by", "reviewer")[0] == 0
    assert pj("update", "T-1", "--verification-result", GREEN, "--status", "in_review", "--by", "dev")[0] == 0


def test_subtask_can_be_cheaper_than_its_parent(pj: Run) -> None:
    add(pj, "T-1")
    pj("add", "--parent", "T-1", "--title", "a", "--verification-cmd", "true", "--profile", "docs", "--by", "human")
    pj("claim", "T-1", "--by", "dev")
    pj("claim", "T-1.1", "--by", "dev")
    pj("update", "T-1.1", "--verification-result", GREEN, "--status", "in_review", "--by", "dev")
    assert pj("update", "T-1.1", "--status", "done", "--by", "dev")[0] == 0


def test_subtask_rules_in_validate(project: Path, pj: Run) -> None:
    add(pj, "T-1")
    pj("add", "--parent", "T-1", "--title", "a", "--verification-cmd", "true", "--by", "human")
    code, _, err = pj("add", "--parent", "T-1.1", "--title", "b", "--verification-cmd", "true", "--by", "human")
    assert code == 1 and "only one level" in err
    code, _, err = pj("add", "--parent", "T-9", "--title", "b", "--verification-cmd", "true", "--by", "human")
    assert code == 1 and "unknown parent" in err
    code, _, err = pj("add", "--title", "b", "--verification-cmd", "true", "--by", "human")
    assert code == 1 and "--parent" in err
    data = registry(project)
    tasks = data["tasks"]
    assert isinstance(tasks, list)
    tasks[0]["status"] = "done"  # hand edit: parent closed over an open subtask
    tasks[0]["verification_result"] = {"ok": True}
    tasks[0]["review_result"] = {"ok": True, "by": "reviewer"}
    errors = validate(data, config.load(project))
    assert any("subtasks are open" in e for e in errors)
    tasks[1]["id"] = "T-7.1"
    assert any("must be '<parent id>.<number>'" in e for e in validate(data, config.load(project)))


def test_move_cannot_put_a_subtask_before_its_parent(pj: Run) -> None:
    add(pj, "T-1")
    add(pj, "T-2")
    pj("add", "--parent", "T-2", "--title", "a", "--verification-cmd", "true", "--by", "human")
    code, _, err = pj("move", "T-2.1", "--before", "T-2", "--by", "human")
    assert code == 1 and "not placed before" in err


def test_render_nests_subtasks(pj: Run, project: Path) -> None:
    add(pj, "T-1", "--profile", "docs")
    pj("add", "--parent", "T-1", "--title", "a", "--verification-cmd", "true", "--by", "human")
    text = (project / ".taskgate" / "tasks.md").read_text(encoding="utf-8")
    assert "| ↳ T-1.1 |" in text and "(0/1 subtasks done)" in text and "`[docs]`" in text
    assert "(0/1 done)" in text
    assert pj("render", "--check")[0] == 0


def test_next_mentions_how_the_task_closes(pj: Run) -> None:
    add(pj, "T-1", "--profile", "docs")
    add(pj, "T-2")
    out = pj("next")[1]
    assert "profile docs, no review, gates docs,tasks" in out


@pytest.mark.parametrize(
    "toml, message",
    [
        ('[profiles.x]\ngates = ["nope"]\n', "unknown gates"),
        ("[profiles.default]\nrequire_review = false\n", "reserved"),
        ("[profiles.x]\nbogus = 1\n", "unknown keys"),
        ('[profiles.x]\nreviewer = ""\n', "non-empty"),
    ],
)
def test_bad_profile_configuration_is_rejected(project: Path, toml: str, message: str) -> None:
    (project / "taskgate.toml").write_text(toml, encoding="utf-8")
    with pytest.raises(SystemExit, match=message):
        config.load(project)


def test_cli_main_exposes_new_commands() -> None:
    parser = cli.build_parser()
    assert parser.parse_args(["show", "T-1"]).func is not None
    assert parser.parse_args(["profile", "T-1", "--clear"]).clear is True


def test_mcp_subtask_show_and_task_scoped_quality(pj: Run) -> None:
    add(pj, "T-1", "--profile", "docs")

    def tool(tool_name: str, **arguments: object) -> tuple[str, bool]:
        return text_of(call("tools/call", {"name": tool_name, "arguments": arguments}))

    text, is_error = tool("task_add", parent="T-1", title="a", verification_cmd="true", by="human")
    assert not is_error and "T-1.1 added" in text
    text, is_error = tool("task_add", title="a", verification_cmd="true", by="human")
    assert is_error and "parent" in text
    text, is_error = tool("task_show", id="T-1.1")
    assert not is_error and json.loads(text)["policy"]["profile"] == "docs"
    text, is_error = tool("task_profile", id="T-1.1", name="light", by="human")
    assert not is_error
    text, is_error = tool("task_profile", id="T-1.1", by="human")
    assert is_error and "exactly one" in text
    text, is_error = tool("quality_check", task="T-1")
    assert not is_error and {r["check"] for r in json.loads(text)["results"]} == {"docs", "tasks"}
    text, is_error = tool("quality_check", task="T-1.1")
    assert not is_error and {r["check"] for r in json.loads(text)["results"]} == {"docs"}
    text, is_error = tool("quality_check", task="T-1", checks=["build"])
    assert is_error and "not both" in text
    text, is_error = tool("quality_check", task="T-99")
    assert is_error and "unknown task" in text
