"""Concurrency-safe storage for the task registry (JSON + JSONL log).

Files under ``<root>/<data_dir>/`` (default ``.taskgate/``):

- ``tasks.json``       -- source of truth (commit it; edit through the CLI)
- ``tasks.log.jsonl``  -- append-only mutation log ({op, task, at, by, detail})
- ``tasks.md``         -- generated Markdown view
- ``.lock``            -- lock file serializing read-modify-write
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import IO, Any

from . import config as config_mod
from . import render
from .config import Config


@dataclass(frozen=True)
class Project:
    """A located project: its root directory and configuration."""

    root: Path
    config: Config

    @property
    def data_dir(self) -> Path:
        """Directory holding the registry files."""
        return self.root / self.config.data_dir

    @property
    def tasks_file(self) -> Path:
        """Path of the JSON registry."""
        return self.data_dir / "tasks.json"

    @property
    def log_file(self) -> Path:
        """Path of the append-only JSONL log."""
        return self.data_dir / "tasks.log.jsonl"

    @property
    def view_file(self) -> Path:
        """Path of the generated Markdown view."""
        return self.data_dir / "tasks.md"


def open_project(*, create: bool = False) -> Project:
    """Locate the project (``create`` = ``init``: use the current directory or ``TASKGATE_ROOT``)."""
    root = config_mod.init_root() if create else config_mod.find_root()
    return Project(root, config_mod.load(root))


def now() -> str:
    """ISO-8601 UTC timestamp with second precision."""
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


if sys.platform == "win32":
    import msvcrt

    def _lock(fh: IO[bytes]) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)

    def _unlock(fh: IO[bytes]) -> None:
        fh.seek(0)
        msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl

    def _lock(fh: IO[bytes]) -> None:
        fcntl.flock(fh, fcntl.LOCK_EX)

    def _unlock(fh: IO[bytes]) -> None:
        fcntl.flock(fh, fcntl.LOCK_UN)


@contextmanager
def locked(project: Project) -> Iterator[None]:
    """Exclusive file lock around registry read-modify-write."""
    project.data_dir.mkdir(parents=True, exist_ok=True)
    with (project.data_dir / ".lock").open("a+b") as fh:
        _lock(fh)
        try:
            yield
        finally:
            _unlock(fh)


def load(project: Project) -> dict[str, Any]:
    """Load the registry; fails cleanly when not initialized."""
    path = project.tasks_file
    if not path.exists():
        raise SystemExit(f"error: {path} not found -- run 'taskgate init' first")
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def save(project: Project, data: dict[str, Any]) -> None:
    """Atomically write the registry (temp file + os.replace) and refresh the Markdown view."""
    path = project.tasks_file
    data["updated"] = now()
    text = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        Path(tmp_name).write_text(text, encoding="utf-8")
        os.replace(tmp_name, path)
    except BaseException:
        os.unlink(tmp_name)
        raise
    finally:
        os.close(fd)
    # keep the view in step with every registry change, so 'render --check' never goes red by itself
    project.view_file.write_text(render.render(data, project.config), encoding="utf-8")


def append_log(project: Project, op: str, task_id: str, by: str, detail: dict[str, Any]) -> None:
    """Append one mutation event to the JSONL log."""
    entry = {"op": op, "task": task_id, "at": now(), "by": by, "detail": detail}
    project.data_dir.mkdir(parents=True, exist_ok=True)
    with project.log_file.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_seed(path: str | Path) -> list[dict[str, Any]]:
    """Read a seed file expecting {'tasks': [...]} or a bare task array."""
    raw = json.loads(Path(path).read_text(encoding="utf-8"))
    tasks = raw.get("tasks") if isinstance(raw, dict) else raw
    if not isinstance(tasks, list):
        raise SystemExit("error: seed file must contain a 'tasks' list")
    return tasks
