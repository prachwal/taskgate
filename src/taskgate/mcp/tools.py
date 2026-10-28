"""MCP tools: thin wrappers over the CLI commands, plus the configurable quality gate."""

from __future__ import annotations

import json
from typing import Any

from .. import config as config_mod
from .. import model
from . import bridge
from .registry import arg, tool

_STATUSES = list(model.STATUSES)


@tool(
    "task_list",
    "List tasks (optional status filter).",
    {"properties": {"status": {"type": "string", "enum": _STATUSES}}},
    read_only=True,
)
def task_list(args: dict[str, Any]) -> str:
    return bridge.run_cli(["list", *(["--status", arg(args, "status")] if arg(args, "status") else [])])


@tool(
    "task_next",
    "Show the one task that may start now: the queue head, planned, with dependencies and the phase gate met.",
    {"properties": {"owner": {"type": "string"}}},
    read_only=True,
)
def task_next(args: dict[str, Any]) -> str:
    return bridge.run_cli(["next", *(["--owner", arg(args, "owner")] if arg(args, "owner") else [])])


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
    "configured reviewer identity, a different one, after the configured delay since the stored verification, "
    "must list the commands it checked in checks=[...]; closing as done needs a fresh review_result in the same "
    "call (unless the project sets require_review = false).",
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
    "task_add",
    "Add a draft/planned task (duplicate ids and closed phases are rejected). Only identities listed in "
    "'planners' of taskgate.toml may add tasks; pass by explicitly.",
    {"properties": {
        "id": {"type": "string"},
        "title": {"type": "string"},
        "phase": {"type": "integer", "minimum": 0},
        "verification_cmd": {"type": "string"},
        "spec": {"type": "string"},
        "status": {"type": "string", "enum": list(model.ADD_STATUSES)},
        "owner": {"type": "string"},
        "depends": {"type": "array", "items": {"type": "string"}},
        "by": {"type": "string"},
    }, "required": ["id", "title", "verification_cmd", "by"]},
)
def task_add(args: dict[str, Any]) -> str:
    argv = ["add", "--id", arg(args, "id"), "--title", arg(args, "title"),
            "--verification-cmd", arg(args, "verification_cmd"), "--by", arg(args, "by")]
    if arg(args, "phase") is not None:
        argv += ["--phase", str(arg(args, "phase"))]
    for key, flag in (("spec", "--spec"), ("status", "--status"), ("owner", "--owner")):
        if arg(args, key):
            argv += [flag, arg(args, key)]
    if arg(args, "depends"):
        argv += ["--depends", ",".join(arg(args, "depends"))]
    return bridge.run_cli(argv)


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


BUILTIN_GATES = ("tasks",)


@tool(
    "quality_check",
    "Run quality gates and return a compact JSON report. Gate names come from [quality] in taskgate.toml; the "
    "built-in gate 'tasks' validates the registry and checks the Markdown view. Without 'checks' every gate runs.",
    {"properties": {"checks": {"type": "array", "items": {"type": "string"}}}},
)
def quality_check(args: dict[str, Any]) -> str:
    gates = config_mod.load(config_mod.find_root()).quality
    available = [*gates, *BUILTIN_GATES]
    requested = arg(args, "checks")
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
