from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from taskgate import cli

Run = Callable[..., tuple[int, str, str]]


@pytest.fixture
def project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """An empty project directory with review delay disabled."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TASKGATE_ROOT", raising=False)
    monkeypatch.delenv("TASKGATE_BY", raising=False)
    (tmp_path / "taskgate.toml").write_text("review_delay_seconds = 0\n", encoding="utf-8")
    return tmp_path


@pytest.fixture
def tg(project: Path, capsys: pytest.CaptureFixture[str]) -> Run:
    """Run a CLI command in the project, returning (exit code, stdout, stderr)."""

    def run(*argv: str) -> tuple[int, str, str]:
        capsys.readouterr()
        code = cli.main(list(argv))
        captured = capsys.readouterr()
        return code, captured.out, captured.err

    return run


def registry(project: Path) -> dict[str, object]:
    data: dict[str, object] = json.loads((project / ".taskgate" / "tasks.json").read_text(encoding="utf-8"))
    return data


def task_of(project: Path, task_id: str) -> dict[str, object]:
    tasks = registry(project)["tasks"]
    assert isinstance(tasks, list)
    return next(t for t in tasks if t["id"] == task_id)  # type: ignore[no-any-return]


GREEN = '{"ok": true}'
REVIEW = '{"ok": true, "by": "reviewer", "checks": ["cmd"]}'


def add(tg: Run, task_id: str, *extra: str, by: str = "human") -> None:
    code, _, err = tg("add", "--id", task_id, "--title", f"title {task_id}", "--verification-cmd", "true", "--by", by, *extra)
    assert code == 0, err


def finish(tg: Run, task_id: str, dev: str = "dev") -> None:
    """Drive a planned task through claim, verification, review to done."""
    assert tg("claim", task_id, "--by", dev)[0] == 0
    assert tg("update", task_id, "--verification-result", GREEN, "--by", dev)[0] == 0
    assert tg("update", task_id, "--status", "in_review", "--by", dev)[0] == 0
    code, _, err = tg("update", task_id, "--status", "done", "--review-result", REVIEW, "--by", "reviewer")
    assert code == 0, err
