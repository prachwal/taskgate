from __future__ import annotations

from pathlib import Path

from conftest import GREEN, REVIEW, Run, add, finish, registry, task_of


def test_init_refuses_to_overwrite(tg: Run) -> None:
    assert tg("init")[0] == 0
    code, _, err = tg("init")
    assert code == 1 and "already exists" in err
    assert tg("init", "--force")[0] == 0


def test_add_requires_a_planner(tg: Run) -> None:
    tg("init")
    code, _, err = tg("add", "--id", "T-1", "--title", "x", "--verification-cmd", "true", "--by", "dev")
    assert code == 1 and "may add tasks" in err


def test_add_rejects_bad_id_and_duplicates(tg: Run) -> None:
    tg("init")
    add(tg, "T-1")
    assert tg("add", "--id", "T-1", "--title", "x", "--verification-cmd", "true")[0] == 1
    code, _, err = tg("add", "--id", "bad id", "--title", "x", "--verification-cmd", "true")
    assert code == 1 and "id must match" in err


def test_full_flow_to_done(tg: Run, project: Path) -> None:
    tg("init")
    add(tg, "T-1")
    finish(tg, "T-1")
    task = task_of(project, "T-1")
    assert task["status"] == "done" and task["review_result"]["by"] == "reviewer"  # type: ignore[index]
    assert (project / ".taskgate" / "tasks.log.jsonl").read_text().count("\n") >= 5


def test_in_review_needs_green_verification(tg: Run) -> None:
    tg("init")
    add(tg, "T-1")
    tg("claim", "T-1", "--by", "dev")
    code, _, err = tg("update", "T-1", "--status", "in_review", "--by", "dev")
    assert code == 1 and "green verification_result" in err


def test_done_needs_review_in_same_call(tg: Run) -> None:
    tg("init")
    add(tg, "T-1")
    tg("claim", "T-1", "--by", "dev")
    tg("update", "T-1", "--verification-result", GREEN, "--by", "dev")
    tg("update", "T-1", "--status", "in_review", "--by", "dev")
    code, _, err = tg("update", "T-1", "--status", "done", "--by", "dev")
    assert code == 1 and "fresh --review-result" in err


def test_review_rules(tg: Run) -> None:
    tg("init")
    add(tg, "T-1")
    tg("claim", "T-1", "--by", "dev")
    tg("update", "T-1", "--verification-result", GREEN, "--by", "dev")
    tg("update", "T-1", "--status", "in_review", "--by", "dev")
    # caller is not the reviewer
    assert "must both be 'reviewer'" in tg("update", "T-1", "--review-result", REVIEW, "--by", "dev")[2]
    # checks are mandatory
    assert "checks" in tg("update", "T-1", "--review-result", '{"ok": true, "by": "reviewer"}', "--by", "reviewer")[2]
    # both results in one call are refused
    code, _, err = tg("update", "T-1", "--verification-result", GREEN, "--review-result", REVIEW, "--by", "reviewer")
    assert code == 1 and "separate update calls" in err


def test_reviewer_cannot_be_the_verifier(tg: Run) -> None:
    tg("init")
    add(tg, "T-1")
    tg("claim", "T-1", "--by", "reviewer")
    tg("update", "T-1", "--verification-result", GREEN, "--by", "reviewer")
    tg("update", "T-1", "--status", "in_review", "--by", "reviewer")
    assert "must differ" in tg("update", "T-1", "--review-result", REVIEW, "--by", "reviewer")[2]


def test_review_delay_is_enforced(tg: Run, project: Path) -> None:
    (project / "taskgate.toml").write_text("review_delay_seconds = 3600\n", encoding="utf-8")
    tg("init")
    add(tg, "T-1")
    tg("claim", "T-1", "--by", "dev")
    tg("update", "T-1", "--verification-result", GREEN, "--by", "dev")
    tg("update", "T-1", "--status", "in_review", "--by", "dev")
    assert "3600 seconds" in tg("update", "T-1", "--review-result", REVIEW, "--by", "reviewer")[2]


def test_fresh_verification_voids_review(tg: Run, project: Path) -> None:
    tg("init")
    add(tg, "T-1")
    tg("claim", "T-1", "--by", "dev")
    tg("update", "T-1", "--verification-result", GREEN, "--by", "dev")
    tg("update", "T-1", "--status", "in_review", "--by", "dev")
    tg("update", "T-1", "--review-result", REVIEW, "--by", "reviewer")
    tg("update", "T-1", "--verification-result", GREEN, "--by", "dev")
    assert "review_result" not in task_of(project, "T-1")


def test_planned_cannot_skip_claim(tg: Run) -> None:
    tg("init")
    add(tg, "T-1")
    code, _, err = tg("update", "T-1", "--status", "in_progress", "--by", "dev")
    assert code == 1 and "claim" in err


def test_invalid_transition_is_refused(tg: Run) -> None:
    tg("init")
    add(tg, "T-1")
    code, _, err = tg("update", "T-1", "--status", "in_review", "--by", "dev")
    assert code == 1 and "not allowed" in err


def test_blocked_needs_reason_and_clears(tg: Run, project: Path) -> None:
    tg("init")
    add(tg, "T-1")
    tg("claim", "T-1", "--by", "dev")
    assert tg("update", "T-1", "--status", "blocked", "--by", "dev")[0] == 1
    assert tg("update", "T-1", "--status", "blocked", "--reason", "waiting", "--by", "dev")[0] == 0
    assert tg("update", "T-1", "--status", "in_progress", "--by", "dev")[0] == 0
    assert "blocked_reason" not in task_of(project, "T-1")


def test_terminal_tasks_are_closed(tg: Run) -> None:
    tg("init")
    add(tg, "T-1")
    finish(tg, "T-1")
    code, _, err = tg("update", "T-1", "--status", "cancelled", "--by", "dev")
    assert code == 1 and "terminal" in err


def test_order_blocks_later_tasks(tg: Run) -> None:
    tg("init")
    add(tg, "T-1")
    add(tg, "T-2")
    code, _, err = tg("claim", "T-2", "--by", "dev")
    assert code == 1 and "order: T-1 comes first" in err
    finish(tg, "T-1")
    assert tg("claim", "T-2", "--by", "dev")[0] == 0


def test_phase_gate(tg: Run) -> None:
    tg("init")
    add(tg, "T-1", "--phase", "0")
    add(tg, "T-2", "--phase", "1")
    code, _, err = tg("claim", "T-2", "--by", "dev")
    assert code == 1 and "phase gate" in err


def test_add_to_closed_phase_is_refused(tg: Run) -> None:
    tg("init")
    add(tg, "T-1", "--phase", "1")
    code, _, err = tg("add", "--id", "T-2", "--title", "x", "--verification-cmd", "true", "--phase", "0")
    assert code == 1 and "already closed" in err


def test_dependencies_must_be_done(tg: Run) -> None:
    tg("init")
    add(tg, "T-1")
    add(tg, "T-2", "--depends", "T-1")
    finish(tg, "T-1")
    assert tg("claim", "T-2", "--by", "dev")[0] == 0


def test_move_and_depends_are_planner_only(tg: Run) -> None:
    tg("init")
    add(tg, "T-1")
    add(tg, "T-2")
    assert tg("move", "T-2", "--before", "T-1", "--by", "dev")[0] == 1
    assert tg("move", "T-2", "--before", "T-1", "--by", "human")[0] == 0
    assert tg("next")[1].startswith("T-2")
    assert tg("depends", "T-1", "--add", "T-2", "--by", "dev")[0] == 1
    assert tg("depends", "T-1", "--add", "T-2", "--by", "human")[0] == 0
    assert tg("depends", "T-1", "--add", "T-1", "--by", "human")[0] == 1


def test_cannot_move_in_front_of_started_work(tg: Run) -> None:
    tg("init")
    add(tg, "T-1")
    add(tg, "T-2")
    tg("claim", "T-1", "--by", "dev")
    code, _, err = tg("move", "T-2", "--before", "T-1", "--by", "human")
    assert code == 1 and "already started" in err


def test_sort_orders_by_phase_then_natural_id(tg: Run, project: Path) -> None:
    tg("init")
    add(tg, "T-10")
    add(tg, "T-2")
    tg("sort")
    ids = [t["id"] for t in registry(project)["tasks"]]  # type: ignore[attr-defined]
    assert ids == ["T-2", "T-10"]


def test_claim_does_not_steal_without_force(tg: Run) -> None:
    tg("init")
    add(tg, "T-1", "--owner", "alice")
    assert tg("claim", "T-1", "--by", "bob")[0] == 1
    assert tg("claim", "T-1", "--by", "bob", "--force")[0] == 0


def test_require_review_false_closes_on_verification(tg: Run, project: Path) -> None:
    (project / "taskgate.toml").write_text("require_review = false\n", encoding="utf-8")
    tg("init")
    add(tg, "T-1")
    tg("claim", "T-1", "--by", "dev")
    tg("update", "T-1", "--verification-result", GREEN, "--by", "dev")
    tg("update", "T-1", "--status", "in_review", "--by", "dev")
    assert tg("update", "T-1", "--status", "done", "--by", "dev")[0] == 0
    assert tg("validate")[0] == 0


def test_validate_catches_hand_edited_done(tg: Run, project: Path) -> None:
    tg("init")
    add(tg, "T-1")
    path = project / ".taskgate" / "tasks.json"
    path.write_text(path.read_text().replace('"planned"', '"done"'), encoding="utf-8")
    code, _, err = tg("validate")
    assert code == 1 and "requires a green verification_result" in err and "review_result" in err


def test_render_check_detects_drift(tg: Run, project: Path) -> None:
    tg("init")
    add(tg, "T-1")
    assert tg("render", "--check")[0] == 0
    (project / ".taskgate" / "tasks.md").write_text("stale\n", encoding="utf-8")
    assert tg("render", "--check")[0] == 1
    assert tg("render")[0] == 0 and tg("render", "--check")[0] == 0


def test_identity_from_environment(tg: Run, project: Path, monkeypatch: object) -> None:
    import pytest

    assert isinstance(monkeypatch, pytest.MonkeyPatch)
    tg("init")
    monkeypatch.setenv("TASKGATE_BY", "carol")
    assert tg("add", "--id", "T-1", "--title", "x", "--verification-cmd", "true")[0] == 1
    monkeypatch.setenv("TASKGATE_BY", "human")
    assert tg("add", "--id", "T-1", "--title", "x", "--verification-cmd", "true")[0] == 0
