"""Helpers shared by the CLI commands."""

from __future__ import annotations

import argparse
import os
from typing import Any

EMPTY_REGISTRY: dict[str, Any] = {"version": 1, "tasks": []}

VERIFICATION_STATUSES = ("in_review", "done")


def identity(args: argparse.Namespace) -> str:
    """Declared caller identity: ``--by``, else ``TASKGATE_BY``, else ``human``."""
    by: str | None = getattr(args, "by", None)
    return by or os.environ.get("TASKGATE_BY", "human")


def find(data: dict[str, Any], task_id: str) -> tuple[dict[str, Any], bool]:
    """The task with this id and whether it exists."""
    for task in data.get("tasks", []):
        if task.get("id") == task_id:
            return task, True
    return {}, False
