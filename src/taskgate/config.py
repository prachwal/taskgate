"""Project configuration: ``taskgate.toml`` at the project root (optional, every key has a default)."""

from __future__ import annotations

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

CONFIG_FILE = "taskgate.toml"
DEFAULT_DATA_DIR = ".taskgate"
DEFAULT_ID_PATTERN = r"^[A-Za-z][A-Za-z0-9]*-\d+$"


@dataclass(frozen=True)
class Config:
    """Policy and layout of one project.

    ``planners`` are the identities allowed to add, move and re-link tasks, and
    ``reviewer`` is the identity whose result closes a task. Identities are
    declared by the caller (``--by`` / ``TASKGATE_BY``): this is a process
    barrier between roles, not authentication.
    """

    data_dir: str = DEFAULT_DATA_DIR
    title: str = "Tasks"
    id_pattern: str = DEFAULT_ID_PATTERN
    phase_names: dict[int, str] = field(default_factory=dict)
    planners: tuple[str, ...] = ("human",)
    reviewer: str = "reviewer"
    owners: tuple[str, ...] | None = None
    require_review: bool = True
    review_delay_seconds: int = 60
    quality: dict[str, list[list[str]]] = field(default_factory=dict)

    @property
    def id_regex(self) -> re.Pattern[str]:
        """Compiled ``id_pattern``; a named group ``phase`` ties the id to the task's phase."""
        return re.compile(self.id_pattern)


def _strings(raw: Any, key: str) -> tuple[str, ...]:
    if not isinstance(raw, list) or not all(isinstance(x, str) and x for x in raw):
        raise SystemExit(f"error: {CONFIG_FILE}: {key} must be a list of non-empty strings")
    return tuple(raw)


def parse(raw: dict[str, Any]) -> Config:
    """Build a ``Config`` from parsed TOML, rejecting unknown keys and bad values."""
    known = {
        "data_dir", "title", "id_pattern", "phase_names", "planners", "reviewer",
        "owners", "require_review", "review_delay_seconds", "quality",
    }
    unknown = sorted(set(raw) - known)
    if unknown:
        raise SystemExit(f"error: {CONFIG_FILE}: unknown keys {', '.join(unknown)}")
    base = Config()
    values: dict[str, Any] = {}
    for key in ("data_dir", "title", "id_pattern", "reviewer"):
        if key in raw:
            if not isinstance(raw[key], str) or not raw[key]:
                raise SystemExit(f"error: {CONFIG_FILE}: {key} must be a non-empty string")
            values[key] = raw[key]
    for key in ("planners", "owners"):
        if key in raw:
            values[key] = _strings(raw[key], key)
    for key in ("require_review",):
        if key in raw:
            if not isinstance(raw[key], bool):
                raise SystemExit(f"error: {CONFIG_FILE}: {key} must be true or false")
            values[key] = raw[key]
    if "review_delay_seconds" in raw:
        delay = raw["review_delay_seconds"]
        if not isinstance(delay, int) or isinstance(delay, bool) or delay < 0:
            raise SystemExit(f"error: {CONFIG_FILE}: review_delay_seconds must be an integer >= 0")
        values["review_delay_seconds"] = delay
    if "phase_names" in raw:
        names = raw["phase_names"]
        if not isinstance(names, dict) or not all(k.isdigit() and isinstance(v, str) for k, v in names.items()):
            raise SystemExit(f"error: {CONFIG_FILE}: phase_names must map phase numbers to strings")
        values["phase_names"] = {int(k): v for k, v in names.items()}
    if "quality" in raw:
        gates = raw["quality"]
        ok = isinstance(gates, dict) and all(
            isinstance(cmds, list) and cmds and all(
                isinstance(c, list) and c and all(isinstance(a, str) for a in c) for c in cmds
            )
            for cmds in gates.values()
        )
        if not ok:
            raise SystemExit(
                f"error: {CONFIG_FILE}: quality.<name> must be a non-empty list of argv arrays"
            )
        values["quality"] = {name: [list(c) for c in cmds] for name, cmds in gates.items()}
    config = Config(**{**base.__dict__, **values})
    try:
        re.compile(config.id_pattern)
    except re.error as exc:
        raise SystemExit(f"error: {CONFIG_FILE}: id_pattern is not a valid regex: {exc}") from exc
    return config


def load(root: Path) -> Config:
    """Read ``taskgate.toml`` from ``root``; defaults when it does not exist."""
    path = root / CONFIG_FILE
    if not path.is_file():
        return Config()
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as exc:
        raise SystemExit(f"error: {path}: {exc}") from exc
    return parse(raw)


def find_root(start: Path | None = None) -> Path:
    """Project root: ``TASKGATE_ROOT``, else the nearest ancestor with a config or data directory."""
    env = os.environ.get("TASKGATE_ROOT")
    if env:
        return Path(env).expanduser().resolve()
    here = (start or Path.cwd()).resolve()
    for parent in (here, *here.parents):
        if (parent / CONFIG_FILE).is_file() or (parent / DEFAULT_DATA_DIR).is_dir():
            return parent
    raise SystemExit(
        "error: no taskgate project found above the current directory "
        "(run 'taskgate init' or set TASKGATE_ROOT)"
    )


def init_root() -> Path:
    """Where ``init`` creates a project: ``TASKGATE_ROOT`` or the current directory."""
    env = os.environ.get("TASKGATE_ROOT")
    return Path(env).expanduser().resolve() if env else Path.cwd().resolve()
