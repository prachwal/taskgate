"""Task data model: statuses, transitions and registry validation."""

from __future__ import annotations

import re
from typing import Any

from .config import DEFAULT_PROFILE, Config, Policy

STATUSES = (
    "draft",
    "planned",
    "in_progress",
    "in_review",
    "blocked",
    "done",
    "cancelled",
)
TERMINAL = frozenset({"done", "cancelled"})
# Started but not finished: such a task is the queue head and nothing may be inserted before it.
IN_FLIGHT = frozenset({"in_progress", "in_review", "blocked"})

TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"planned", "cancelled"}),
    "planned": frozenset({"in_progress", "cancelled"}),
    "in_progress": frozenset({"in_review", "blocked", "cancelled"}),
    "blocked": frozenset({"in_progress", "cancelled"}),
    "in_review": frozenset({"done", "in_progress", "cancelled"}),
    "done": frozenset(),
    "cancelled": frozenset(),
}

REQUIRED_FIELDS = ("id", "title", "status", "verification_cmd")
OPTIONAL_FIELDS = (
    "phase",
    "owner",
    "depends_on",
    "spec_source",
    "verification_result",
    "review_result",
    "blocked_reason",
    "notes",
    "links",
    "parent",
    "profile",
    "created",
    "updated",
    "started",
    "finished",
)

#: Statuses a new task may start in; work starts through ``claim``.
ADD_STATUSES = ("draft", "planned")


class ValidationError(ValueError):
    """Raised when a task or registry violates the schema or flow rules."""


def can_transition(current: str, new: str) -> bool:
    """Return True when the status change is allowed."""
    return new in TRANSITIONS.get(current, frozenset())


def is_green(result: Any) -> bool:
    """True when a verification or review result is a dict with ``ok: true``."""
    return isinstance(result, dict) and result.get("ok") is True


def is_review(result: Any, reviewer: str) -> bool:
    """True when a result is green and carries the configured reviewer identity."""
    return is_green(result) and result.get("by") == reviewer


def parent_of(task: dict[str, Any]) -> str | None:
    """Id of the task's parent, or ``None`` for a top-level task."""
    parent = task.get("parent")
    return parent if isinstance(parent, str) and parent else None


def subtasks_of(tasks: list[Any], task_id: str) -> list[dict[str, Any]]:
    """The direct subtasks of ``task_id`` in registry order."""
    return [t for t in tasks if isinstance(t, dict) and parent_of(t) == task_id]


def profile_name(task: dict[str, Any], by_id: dict[str, dict[str, Any]]) -> str | None:
    """The task's own profile, else its parent's; ``None`` selects the project-wide default."""
    own = task.get("profile")
    if isinstance(own, str) and own:
        return own
    parent = by_id.get(parent_of(task) or "")
    if parent is not None:
        inherited = parent.get("profile")
        if isinstance(inherited, str) and inherited:
            return inherited
    return None


def policy_of(task: dict[str, Any], tasks: list[Any], config: Config) -> Policy:
    """How ``task`` is closed: review requirement, reviewer identity, delay and quality gates."""
    by_id = {t["id"]: t for t in tasks if isinstance(t, dict) and isinstance(t.get("id"), str)}
    return config.policy(profile_name(task, by_id))


def phase_of(task: dict[str, Any]) -> int:
    """The task's phase; tasks without one are in phase 0."""
    phase = task.get("phase", 0)
    return phase if isinstance(phase, int) and not isinstance(phase, bool) else 0


def _validate_task(task: dict[str, Any], config: Config, by_id: dict[str, dict[str, Any]]) -> list[str]:
    errors: list[str] = []
    tid = task.get("id", "<missing>")
    parent = parent_of(task)
    if parent is not None and isinstance(tid, str):
        # a subtask id is <parent id>.<n>; the parent id itself follows id_pattern, the phase comes from the parent
        suffix = re.fullmatch(re.escape(parent) + r"\.\d+", tid)
        match = config.id_regex.fullmatch(parent) if suffix else None
        if match is None:
            errors.append(f"{tid}: a subtask id must be '<parent id>.<number>' (parent {parent!r})")
            return errors
        match = None
    else:
        match = config.id_regex.fullmatch(tid) if isinstance(tid, str) else None
        if match is None:
            errors.append(f"{tid}: id must match {config.id_pattern}")
            return errors
    for name in REQUIRED_FIELDS:
        value = task.get(name)
        if not isinstance(value, str) or not value:
            errors.append(f"{tid}: field {name!r} is required (non-empty string)")
    phase = task.get("phase", 0)
    if not isinstance(phase, int) or isinstance(phase, bool) or phase < 0:
        errors.append(f"{tid}: phase must be an integer >= 0")
    elif (
        match is not None
        and "phase" in match.groupdict()
        and match.group("phase") is not None
        and phase != int(match.group("phase"))
    ):
        errors.append(f"{tid}: phase {phase} does not match the id")
    status = task.get("status")
    if status not in STATUSES:
        errors.append(f"{tid}: unknown status {status!r}")
    owner = task.get("owner")
    if owner is not None and config.owners is not None and owner not in config.owners:
        errors.append(f"{tid}: unknown owner {owner!r}")
    deps = task.get("depends_on", [])
    if not isinstance(deps, list) or not all(isinstance(d, str) for d in deps):
        errors.append(f"{tid}: depends_on must be a list of task ids")
    if task.get("blocked_reason") is not None and status != "blocked":
        errors.append(f"{tid}: blocked_reason set but status is {status!r}")
    if status == "blocked" and not task.get("blocked_reason"):
        errors.append(f"{tid}: blocked requires non-empty blocked_reason")
    if status in ("in_review", "done") and not is_green(task.get("verification_result")):
        errors.append(f"{tid}: status {status!r} requires a green verification_result")
    own_profile = task.get("profile")
    if own_profile is not None and (
        not isinstance(own_profile, str)
        or not own_profile
        or (own_profile != DEFAULT_PROFILE and own_profile not in config.profiles)
    ):
        errors.append(f"{tid}: unknown profile {own_profile!r} (known: {', '.join(sorted(config.profiles)) or 'none'})")
    policy = config.policy(profile_name(task, by_id))
    if status == "done" and policy.require_review and not is_review(task.get("review_result"), policy.reviewer):
        errors.append(
            f"{tid}: status 'done' requires a green review_result "
            f"({{'ok': true, 'by': '{policy.reviewer}', ...}})"
        )
    if not isinstance(task.get("notes", []), list):
        errors.append(f"{tid}: notes must be a list")
    if not isinstance(task.get("links", []), list):
        errors.append(f"{tid}: links must be a list")
    return errors


def validate(data: dict[str, Any], config: Config) -> list[str]:
    """Validate the whole registry JSON. Returns a list of error strings."""
    if not isinstance(data, dict):
        return ["registry root must be a JSON object"]
    tasks = data.get("tasks")
    if not isinstance(tasks, list):
        return ["registry must contain a 'tasks' list"]
    errors: list[str] = []
    version = data.get("version", 1)
    if version != 1:
        errors.append(f"unsupported registry version {version!r}")
    known: dict[str, dict[str, Any]] = {}
    by_id = {t["id"]: t for t in tasks if isinstance(t, dict) and isinstance(t.get("id"), str)}
    phases = [phase_of(t) for t in tasks if isinstance(t, dict)]
    if phases != sorted(phases):
        errors.append("tasks are not grouped by ascending phase (reorder with 'move' or run 'taskgate sort')")
    position = {t["id"]: i for i, t in enumerate(tasks) if isinstance(t, dict) and isinstance(t.get("id"), str)}
    for task in tasks:
        if not isinstance(task, dict):
            errors.append("each task must be a JSON object")
            continue
        errors.extend(_validate_task(task, config, by_id))
        tid = task.get("id")
        if isinstance(tid, str):
            if tid in known:
                errors.append(f"{tid}: duplicate task id")
            known[tid] = task
    allowed = set(REQUIRED_FIELDS) | set(OPTIONAL_FIELDS)
    for task in tasks:
        if not isinstance(task, dict):
            continue
        tid = task.get("id", "<missing>")
        for dep in task.get("depends_on") or []:
            if dep not in known:
                errors.append(f"{tid}: depends_on references unknown task {dep!r}")
            elif position.get(dep, 0) >= position.get(tid, 0):
                errors.append(f"{tid}: depends_on {dep!r}, which is not placed before it")
        errors.extend(f"{tid}: unknown field {name!r}" for name in task if name not in allowed)
        errors.extend(_validate_hierarchy(task, known, position, tasks))
    return errors


def _validate_hierarchy(
    task: dict[str, Any], known: dict[str, dict[str, Any]], position: dict[str, int], tasks: list[Any]
) -> list[str]:
    """Parent/subtask rules: one level, same phase, parent first, and no task closes over open subtasks."""
    tid = task.get("id", "<missing>")
    errors: list[str] = []
    status = task.get("status")
    parent_id = parent_of(task)
    if parent_id is not None:
        parent = known.get(parent_id)
        if parent is None:
            return [f"{tid}: parent {parent_id!r} does not exist"]
        if parent_of(parent) is not None:
            errors.append(f"{tid}: parent {parent_id!r} is itself a subtask (only one level is allowed)")
        if position.get(parent_id, 0) >= position.get(tid, 0):
            errors.append(f"{tid}: parent {parent_id!r} is not placed before it")
        if phase_of(parent) != phase_of(task):
            errors.append(f"{tid}: phase {phase_of(task)} differs from its parent's phase {phase_of(parent)}")
        if status in IN_FLIGHT and parent.get("status") not in ("in_progress", "blocked"):
            errors.append(f"{tid}: is {status!r} but its parent {parent_id} is {parent.get('status')!r}, not 'in_progress'")
    if status in ("in_review", "done", "cancelled"):
        open_children = [c["id"] for c in subtasks_of(tasks, str(tid)) if c.get("status") not in TERMINAL]
        if open_children:
            errors.append(f"{tid}: is {status!r} while subtasks are open: {', '.join(open_children)}")
    return errors
