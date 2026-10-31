"""Registry text commands: edit, note, log and doctor."""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from .. import config as config_mod
from .. import model, render, store
from .common import find, identity

EDITABLE_STATUSES = ("draft", "planned")


def cmd_edit(args: argparse.Namespace) -> int:
    """Change the title, spec anchor or verification command of a draft/planned task (planners only)."""
    project = store.open_project()
    by = identity(args)
    if by not in project.config.planners:
        print(f"error: only {', '.join(project.config.planners)} may edit tasks (got {by!r})", file=sys.stderr)
        return 1
    changes = {
        key: value
        for key, value in (("title", args.title), ("spec_source", args.spec), ("verification_cmd", args.verification_cmd))
        if value is not None
    }
    if not changes:
        print("error: pass at least one of --title, --spec, --verification-cmd", file=sys.stderr)
        return 1
    with store.locked(project):
        data = store.load(project)
        task, found = find(data, args.id)
        if not found:
            print(f"error: unknown task {args.id}", file=sys.stderr)
            return 1
        status = task.get("status")
        if status not in EDITABLE_STATUSES:
            print(f"error: {args.id} is {status!r}; only draft/planned tasks can be edited (use 'note')", file=sys.stderr)
            return 1
        before = {key: task.get(key) for key in changes}
        task.update(changes)
        if task.get("spec_source") == "":
            del task["spec_source"]
        errors = model.validate(data, project.config)
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        store.save(project, data)
        store.append_log(project, "edit", args.id, by, {"changed": sorted(changes), "before": before})
    print(f"{args.id} edited ({', '.join(sorted(changes))})")
    return 0


def cmd_note(args: argparse.Namespace) -> int:
    """Append a timestamped note to any task, whatever its status."""
    project = store.open_project()
    by = identity(args)
    text = args.text.strip()
    if not text:
        print("error: note text must not be blank", file=sys.stderr)
        return 1
    with store.locked(project):
        data = store.load(project)
        task, found = find(data, args.id)
        if not found:
            print(f"error: unknown task {args.id}", file=sys.stderr)
            return 1
        task.setdefault("notes", []).append({"at": store.now(), "by": by, "text": text})
        store.save(project, data)
        store.append_log(project, "note", args.id, by, {"text": text})
    print(f"{args.id}: note added")
    return 0


def _read_log(project: store.Project) -> list[dict[str, Any]]:
    path = project.log_file
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict):
            entries.append(entry)
    return entries


def cmd_log(args: argparse.Namespace) -> int:
    """Show the append-only mutation log, newest last, optionally filtered."""
    project = store.open_project()
    entries = [
        e
        for e in _read_log(project)
        if (not args.task or e.get("task") == args.task or str(e.get("task", "")).startswith(f"{args.task}."))
        and (not args.by or e.get("by") == args.by)
    ]
    if args.limit:
        entries = entries[-args.limit :]
    if args.json:
        print(json.dumps(entries, indent=2, ensure_ascii=False))
        return 0
    for e in entries:
        detail = json.dumps(e.get("detail", {}), ensure_ascii=False)
        print(f"{e.get('at', '?')}  {e.get('op', '?'):8}  {e.get('task', '-'):10}  {e.get('by', '?'):10}  {detail}")
    print(f"-- {len(entries)} event(s)")
    return 0


def cmd_doctor(_args: argparse.Namespace) -> int:
    """Check the project setup and report what is wrong; the first command to run when a client finds no project."""
    problems = 0

    def report(ok: bool, text: str) -> None:
        nonlocal problems
        problems += 0 if ok else 1
        print(f"{'ok  ' if ok else 'FAIL'}  {text}")

    try:
        root = config_mod.find_root()
    except SystemExit as exc:
        print(f"FAIL  {str(exc).removeprefix('error: ')}")
        return 1
    print(f"root  {root}")
    try:
        project = store.open_project()
    except (ValueError, SystemExit) as exc:
        report(False, f"configuration is invalid: {str(exc).removeprefix('error: ')}")
        return 1
    config_file = root / config_mod.CONFIG_FILE
    report(True, f"configuration: {config_file if config_file.is_file() else 'defaults (no taskgate.toml)'}")
    if not project.tasks_file.is_file():
        report(False, f"{project.tasks_file} not found (run 'taskgate init')")
        return 1
    data = store.load(project)
    tasks = data.get("tasks", [])
    report(True, f"registry: {project.tasks_file} ({len(tasks)} tasks)")
    errors = model.validate(data, project.config)
    report(not errors, "registry valid" if not errors else f"registry has {len(errors)} error(s); first: {errors[0]}")
    view = project.view_file
    if not view.is_file():
        report(False, f"{view} missing (run 'taskgate render')")
    else:
        in_sync = view.read_text(encoding="utf-8") == render.render(data, project.config)
        report(in_sync, "view in sync" if in_sync else f"{view} drifted from tasks.json (run 'taskgate render')")
    report(project.log_file.is_file(), f"log: {project.log_file}" if project.log_file.is_file() else "log file missing")
    reviewer = project.config.policy(None).reviewer
    print(f"info  planners {', '.join(project.config.planners)}; default reviewer {reviewer}")
    return 1 if problems else 0
