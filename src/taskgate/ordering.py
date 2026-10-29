"""Execution order of the registry: queue head, current phase and claim gates."""

from __future__ import annotations

import re
from typing import Any

from .config import Config
from .model import IN_FLIGHT, TERMINAL, parent_of, phase_of, subtasks_of, validate

MOVABLE = frozenset({"draft", "planned"})


def _natural(text: str) -> list[tuple[int, int, str]]:
    """Sort key splitting digit runs, so ``T-2`` sorts before ``T-10``."""
    return [(0, int(p), "") if p.isdigit() else (1, 0, p) for p in re.split(r"(\d+)", text) if p]


def sorted_tasks(tasks: list[Any]) -> list[Any]:
    """Tasks sorted by phase, then id; the ``sort`` command's order, not the execution order."""
    def key(task: Any) -> tuple[int, list[tuple[int, int, str]]]:
        return (phase_of(task), _natural(str(task.get("id", "")))) if isinstance(task, dict) else (0, [])

    return sorted(tasks, key=key)


def execution_order(tasks: list[Any]) -> list[dict[str, Any]]:
    """Tasks in execution order: their position in the registry (``move`` changes it)."""
    return [task for task in tasks if isinstance(task, dict)]


def queue_head(tasks: list[Any]) -> dict[str, Any] | None:
    """First task in execution order that is not terminal, or None when all are.

    A started parent hands the queue to its first open subtask: that is the work to do next.
    """
    for task in execution_order(tasks):
        if task.get("status") in TERMINAL:
            continue
        if task.get("status") in IN_FLIGHT:
            open_children = [c for c in subtasks_of(tasks, str(task.get("id"))) if c.get("status") not in TERMINAL]
            if open_children:
                return open_children[0]
        return task
    return None


def current_phase(tasks: list[Any]) -> int:
    """Phase of the queue head; the highest phase present once everything is terminal."""
    head = queue_head(tasks)
    if head is not None:
        return phase_of(head)
    return max((phase_of(t) for t in execution_order(tasks)), default=0)


def claim_blockers(data: dict[str, Any], task: dict[str, Any], config: Config) -> list[str]:
    """Reasons ``task`` may not be started now; empty when claiming is allowed.

    Execution is strictly ordered: every task before it must be terminal. For a
    task in a later phase that is the phase gate: all earlier phases are closed
    and the whole registry passes ``validate`` (green verification, and review
    evidence on every ``done`` task when review is required).
    """
    reasons = [f"registry invalid: {e}" for e in validate(data, config)]
    tasks = data.get("tasks", [])
    parent_id = parent_of(task)
    by_id = {t.get("id"): t for t in execution_order(tasks)}
    if parent_id is not None and by_id.get(parent_id, {}).get("status") != "in_progress":
        reasons.append(
            f"parent {parent_id} is {by_id.get(parent_id, {}).get('status')!r}; claim the parent first, "
            "subtasks start only while it is in_progress"
        )
    for earlier in execution_order(tasks):
        if earlier.get("id") == task.get("id"):
            break
        if earlier.get("status") in TERMINAL or earlier.get("id") == parent_id:
            continue
        if phase_of(earlier) != phase_of(task):
            reasons.append(
                f"phase gate: phase {phase_of(earlier)} is not closed "
                f"({earlier.get('id')} is {earlier.get('status')!r})"
            )
        else:
            reasons.append(f"order: {earlier.get('id')} comes first and is {earlier.get('status')!r}")
    statuses = {t.get("id"): t.get("status") for t in execution_order(tasks)}
    for dep in task.get("depends_on") or []:
        if statuses.get(dep) != "done":
            reasons.append(f"dependency {dep} is {statuses.get(dep)!r}, not 'done'")
    return reasons


def move_blockers(tasks: list[Any], task_id: str, anchor_id: str, after: bool) -> list[str]:
    """Reasons ``task_id`` may not be placed before/after ``anchor_id``; empty when the move is allowed.

    Only tasks that have not started can move, and never in front of a task that is
    in flight or done: execution history stays where it happened.
    """
    ordered = execution_order(tasks)
    by_id = {t.get("id"): t for t in ordered}
    if task_id not in by_id:
        return [f"unknown task {task_id}"]
    if anchor_id not in by_id:
        return [f"unknown task {anchor_id}"]
    if task_id == anchor_id:
        return ["a task cannot be moved relative to itself"]
    status = by_id[task_id].get("status")
    if status not in MOVABLE:
        return [f"{task_id} is {status!r}; only {', '.join(sorted(MOVABLE))} tasks can be moved"]
    rest = [t for t in ordered if t.get("id") != task_id]
    index = next(i for i, t in enumerate(rest) if t.get("id") == anchor_id) + (1 if after else 0)
    return [
        f"{t.get('id')} is {t.get('status')!r} and already started or finished; "
        f"{task_id} cannot be placed in front of it"
        for t in rest[index:]
        if t.get("status") in IN_FLIGHT or t.get("status") == "done"
    ]


def moved(tasks: list[Any], task_id: str, anchor_id: str, after: bool) -> list[Any]:
    """The task list with ``task_id`` placed before/after ``anchor_id``; callers check ``move_blockers`` first."""
    ordered = execution_order(tasks)
    task = next(t for t in ordered if t.get("id") == task_id)
    rest = [t for t in ordered if t.get("id") != task_id]
    index = next(i for i, t in enumerate(rest) if t.get("id") == anchor_id) + (1 if after else 0)
    return [*rest[:index], task, *rest[index:]]


def subtask_position(tasks: list[Any], parent_id: str) -> int:
    """Index where a new subtask of ``parent_id`` goes: right after the parent's last subtask (or the parent)."""
    last = -1
    for index, task in enumerate(tasks):
        if isinstance(task, dict) and (task.get("id") == parent_id or parent_of(task) == parent_id):
            last = index
    return last + 1


def next_subtask_id(tasks: list[Any], parent_id: str) -> str:
    """``<parent>.<n>`` with n one above the highest existing subtask number."""
    numbers = [int(str(t["id"]).rsplit(".", 1)[1]) for t in subtasks_of(tasks, parent_id)]
    return f"{parent_id}.{max(numbers, default=0) + 1}"


def insert_position(tasks: list[Any], phase: int) -> int:
    """Index where a new task of ``phase`` goes: after the last task of that or any earlier phase."""
    last = -1
    for index, task in enumerate(tasks):
        if isinstance(task, dict) and phase_of(task) <= phase:
            last = index
    return last + 1
