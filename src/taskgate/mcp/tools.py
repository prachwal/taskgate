"""MCP tools: thin wrappers over the CLI commands, plus the configurable quality gate."""

from __future__ import annotations

import json
from typing import Any

from .. import model, store
from ..config import BUILTIN_GATES
from . import bridge
from .registry import arg, tool

_STATUSES = list(model.STATUSES)


@tool(
    "task_list",
    "List tasks (optional status filter); json=true returns the task records as a JSON array.",
    {"properties": {"status": {"type": "string", "enum": _STATUSES}, "json": {"type": "boolean"}}},
    read_only=True,
)
def task_list(args: dict[str, Any]) -> str:
    argv = ["list", *(["--status", arg(args, "status")] if arg(args, "status") else [])]
    return bridge.run_cli([*argv, *(["--json"] if arg(args, "json") else [])])


@tool(
    "task_next",
    "Show the one task that may start now: the queue head, planned, with dependencies and the phase gate met.",
    {"properties": {"owner": {"type": "string"}, "json": {"type": "boolean"}}},
    read_only=True,
)
def task_next(args: dict[str, Any]) -> str:
    argv = ["next", *(["--owner", arg(args, "owner")] if arg(args, "owner") else [])]
    return bridge.run_cli([*argv, *(["--json"] if arg(args, "json") else [])])


@tool(
    "task_claim",
    "Claim a planned task (-> in_progress, sets owner and started). Refused unless every earlier task is "
    "done/cancelled (order and phase gate) and its dependencies are done.",
    {"properties": {"id": {"type": "string"}, "by": {"type": "string"}, "force": {"type": "boolean"}},
     "required": ["id"]},
)
def task_claim(args: dict[str, Any]) -> str:
    argv = ["claim", arg(args, "id")]
    if arg(args, "by"):
        argv += ["--by", arg(args, "by")]
    if arg(args, "force"):
        argv.append("--force")
    return bridge.run_cli(argv)


@tool(
    "task_update",
    "Advance a task's status and record evidence (transitions are enforced). Send verification_result and "
    "review_result in SEPARATE calls: the caller identity (by) is the verifier; a review must come from the "
    "reviewer identity of the task's profile (see task_show), a different one, after that profile's delay since "
    "the stored verification, and must list the commands it checked in checks=[...]; closing as done needs a "
    "fresh review_result in the same call, unless the task's profile sets require_review = false. A task with "
    "open subtasks cannot go to in_review, done or cancelled.",
    {"properties": {
        "id": {"type": "string"},
        "status": {"type": "string", "enum": _STATUSES},
        "reason": {"type": "string"},
        "verification_result": {"type": "object"},
        "review_result": {"type": "object"},
        "by": {"type": "string"},
    }, "required": ["id"]},
)
def task_update(args: dict[str, Any]) -> str:
    argv = ["update", arg(args, "id")]
    for key, flag in (("status", "--status"), ("reason", "--reason"), ("by", "--by")):
        if arg(args, key):
            argv += [flag, arg(args, key)]
    for key, flag in (("verification_result", "--verification-result"), ("review_result", "--review-result")):
        if arg(args, key) is not None:
            argv += [flag, json.dumps(arg(args, key))]
    return bridge.run_cli(argv)


@tool(
    "task_render",
    "Render the Markdown view from tasks.json; check=true fails on drift instead of writing.",
    {"properties": {"check": {"type": "boolean", "default": False}}},
)
def task_render(args: dict[str, Any]) -> str:
    return bridge.run_cli(["render", *(["--check"] if arg(args, "check", False) else [])])


@tool("task_validate", "Validate tasks.json: schema, status transitions and evidence gates.", {"properties": {}},
      read_only=True)
def task_validate(args: dict[str, Any]) -> str:
    return bridge.run_cli(["validate"])


@tool(
    "task_show",
    "One task with its effective closing policy (profile, whether a review is required and by whom, review delay, "
    "quality gates) and its subtasks. Read it before verifying or reviewing to know what that task needs.",
    {"properties": {"id": {"type": "string"}}, "required": ["id"]},
    read_only=True,
)
def task_show(args: dict[str, Any]) -> str:
    return bridge.run_cli(["show", arg(args, "id")])


@tool(
    "task_profile",
    "Set or clear the review/verification profile of a draft/planned task (profiles are defined in taskgate.toml, "
    "e.g. a docs profile without review). Not allowed once the task has started. Planners only; pass name or "
    "clear=true.",
    {"properties": {"id": {"type": "string"}, "name": {"type": "string"}, "clear": {"type": "boolean"},
                    "by": {"type": "string"}}, "required": ["id", "by"]},
)
def task_profile(args: dict[str, Any]) -> str:
    name, clear = arg(args, "name"), bool(arg(args, "clear", False))
    if bool(name) == clear:
        raise ValueError("pass exactly one of name or clear=true")
    return bridge.run_cli(["profile", arg(args, "id"), *([name] if name else ["--clear"]), "--by", arg(args, "by")])


@tool(
    "task_add",
    "Add a draft/planned task or, with parent, a subtask (id <parent>.<n> assigned when id is omitted; one level, "
    "phase and default profile come from the parent; the parent must be in_progress before a subtask can start, "
    "and cannot close while subtasks are open). profile picks a review/verification profile from taskgate.toml. "
    "Duplicate ids and closed phases are rejected. Only identities listed in 'planners' may add tasks; pass by "
    "explicitly.",
    {"properties": {
        "id": {"type": "string"},
        "parent": {"type": "string"},
        "profile": {"type": "string"},
        "title": {"type": "string"},
        "phase": {"type": "integer", "minimum": 0},
        "verification_cmd": {"type": "string"},
        "spec": {"type": "string"},
        "status": {"type": "string", "enum": list(model.ADD_STATUSES)},
        "owner": {"type": "string"},
        "depends": {"type": "array", "items": {"type": "string"}},
        "by": {"type": "string"},
    }, "required": ["title", "verification_cmd", "by"]},
)
def task_add(args: dict[str, Any]) -> str:
    if not arg(args, "id") and not arg(args, "parent"):
        raise ValueError("pass id, or parent to add a subtask with the next free id")
    argv = ["add", "--title", arg(args, "title"),
            "--verification-cmd", arg(args, "verification_cmd"), "--by", arg(args, "by")]
    for key, flag in (("id", "--id"), ("parent", "--parent"), ("profile", "--profile")):
        if arg(args, key):
            argv += [flag, arg(args, key)]
    if arg(args, "phase") is not None:
        argv += ["--phase", str(arg(args, "phase"))]
    for key, flag in (("spec", "--spec"), ("status", "--status"), ("owner", "--owner")):
        if arg(args, key):
            argv += [flag, arg(args, key)]
    if arg(args, "depends"):
        argv += ["--depends", ",".join(arg(args, "depends"))]
    return bridge.run_cli(argv)


@tool(
    "task_edit",
    "Change the title, spec_source (path + section; empty string clears it) or verification_cmd of a draft/planned "
    "task. Planners only; pass at least one of title, spec, verification_cmd. Started tasks take task_note instead.",
    {"properties": {"id": {"type": "string"}, "title": {"type": "string"}, "spec": {"type": "string"},
                    "verification_cmd": {"type": "string"}, "by": {"type": "string"}}, "required": ["id", "by"]},
)
def task_edit(args: dict[str, Any]) -> str:
    argv = ["edit", arg(args, "id"), "--by", arg(args, "by")]
    for key, flag in (("title", "--title"), ("spec", "--spec"), ("verification_cmd", "--verification-cmd")):
        if arg(args, key) is not None:
            argv += [flag, arg(args, key)]
    return bridge.run_cli(argv)


@tool(
    "task_note",
    "Append a timestamped note to a task in any status (decisions, follow-ups, reasons). Does not change status.",
    {"properties": {"id": {"type": "string"}, "text": {"type": "string"}, "by": {"type": "string"}},
     "required": ["id", "text"]},
)
def task_note(args: dict[str, Any]) -> str:
    return bridge.run_cli(["note", arg(args, "id"), arg(args, "text"), *(["--by", arg(args, "by")] if arg(args, "by") else [])])


@tool(
    "task_log",
    "The append-only mutation log as a JSON array, optionally for one task (subtasks included), one identity, "
    "or the last N events.",
    {"properties": {"task": {"type": "string"}, "by": {"type": "string"}, "limit": {"type": "integer", "minimum": 1}}},
    read_only=True,
)
def task_log(args: dict[str, Any]) -> str:
    argv = ["log", "--json"]
    for key, flag in (("task", "--task"), ("by", "--by")):
        if arg(args, key):
            argv += [flag, arg(args, key)]
    if arg(args, "limit"):
        argv += ["--limit", str(arg(args, "limit"))]
    return bridge.run_cli(argv)


@tool("task_doctor", "Diagnose the project: root, configuration, registry validity, view drift and log.",
      {"properties": {}}, read_only=True)
def task_doctor(args: dict[str, Any]) -> str:
    return bridge.run_cli(["doctor"])


@tool(
    "task_sort",
    "Reset the execution order to phase, then id; discards any order set with task_move.",
    {"properties": {"by": {"type": "string"}}},
)
def task_sort(args: dict[str, Any]) -> str:
    return bridge.run_cli(["sort", *(["--by", arg(args, "by")] if arg(args, "by") else [])])


@tool(
    "task_move",
    "Change the execution order: place a draft/planned task directly before or after another. Never in front "
    "of a task that is in flight or done, and phases stay ascending. Planners only; pass exactly one of "
    "before/after.",
    {"properties": {"id": {"type": "string"}, "before": {"type": "string"}, "after": {"type": "string"},
                    "by": {"type": "string"}}, "required": ["id", "by"]},
)
def task_move(args: dict[str, Any]) -> str:
    before, after = arg(args, "before"), arg(args, "after")
    if bool(before) == bool(after):
        raise ValueError("pass exactly one of before or after")
    return bridge.run_cli(["move", arg(args, "id"), "--before" if before else "--after", before or after,
                           "--by", arg(args, "by")])


@tool(
    "task_depends",
    "Change the dependencies of a draft/planned task: set (replace; [] clears), add and/or remove ids. Each "
    "dependency must exist and be placed before the task (use task_move first). Planners only.",
    {"properties": {
        "id": {"type": "string"},
        "set": {"type": "array", "items": {"type": "string"}},
        "add": {"type": "array", "items": {"type": "string"}},
        "remove": {"type": "array", "items": {"type": "string"}},
        "by": {"type": "string"},
    }, "required": ["id", "by"]},
)
def task_depends(args: dict[str, Any]) -> str:
    argv = ["depends", arg(args, "id")]
    for key in ("set", "add", "remove"):
        if arg(args, key) is not None:
            argv += [f"--{key}", ",".join(arg(args, key))]
    return bridge.run_cli([*argv, "--by", arg(args, "by")])


@tool(
    "quality_check",
    "Run quality gates and return a compact JSON report. Gate names come from [quality] in taskgate.toml; the "
    "built-in gate 'tasks' validates the registry and checks the Markdown view. Without 'checks' every gate runs; "
    "with task=<id> only the gates of that task's profile run (a docs task can skip the build and test gates).",
    {"properties": {"checks": {"type": "array", "items": {"type": "string"}}, "task": {"type": "string"}}},
)
def quality_check(args: dict[str, Any]) -> str:
    project = store.open_project()
    gates = project.config.quality
    available = [*gates, *BUILTIN_GATES]
    requested = arg(args, "checks")
    if requested is not None and arg(args, "task"):
        raise ValueError("pass checks or task, not both")
    if arg(args, "task"):
        tasks = store.load(project).get("tasks", [])
        task = next((t for t in tasks if t.get("id") == arg(args, "task")), None)
        if task is None:
            raise ValueError(f"unknown task {arg(args, 'task')}")
        chosen = model.policy_of(task, tasks, project.config).gates
        requested = list(chosen) if chosen is not None else None
    if requested is None:
        requested = available
    if not requested:
        raise ValueError("checks must contain at least one gate")
    unknown = [name for name in requested if name not in available]
    if unknown:
        raise ValueError(f"unknown quality checks: {', '.join(unknown)} (available: {', '.join(available)})")
    results: list[dict[str, Any]] = []
    ok = True
    for name in requested:
        if name in BUILTIN_GATES:
            for command in (["validate"], ["render", "--check"]):
                try:
                    code, output = 0, bridge.run_cli(command)
                except RuntimeError as exc:
                    code, output = 1, str(exc)
                ok = ok and code == 0
                results.append({"check": name, "command": f"taskgate {' '.join(command)}", "exit": code, "output": output})
            continue
        for command in gates[name]:
            code, output = bridge.run_process(command)
            ok = ok and code == 0
            results.append({"check": name, "command": " ".join(command), "exit": code, "output": output})
    report = json.dumps({"ok": ok, "results": results}, ensure_ascii=False, indent=1)
    if not ok:
        raise RuntimeError(report)
    return report
