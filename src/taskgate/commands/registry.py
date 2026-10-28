"""Registry maintenance commands: init, validate, render, sort."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .. import model, ordering, render, store
from .common import EMPTY_REGISTRY, identity


def cmd_init(args: argparse.Namespace) -> int:
    project = store.open_project(create=True)
    path = project.tasks_file
    if path.exists() and not args.force:
        print(f"error: {path} already exists (use --force to overwrite)", file=sys.stderr)
        return 1
    tasks = store.read_seed(args.seed) if args.seed else EMPTY_REGISTRY["tasks"]
    with store.locked(project):
        store.save(project, {"version": 1, "tasks": tasks})
        store.append_log(project, "init", "-", identity(args), {"seed": args.seed or "-"})
    print(f"initialized {path} ({len(tasks)} tasks)")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    project = store.open_project()
    data = store.load(project)
    errors = model.validate(data, project.config)
    if errors:
        for error in errors:
            print(f"ERROR: {error}", file=sys.stderr)
        return 1
    print(f"OK: {len(data.get('tasks', []))} tasks, schema + flow rules valid")
    return 0


def cmd_render(args: argparse.Namespace) -> int:
    project = store.open_project()
    data = store.load(project)
    text = render.render(data, project.config)
    path = project.view_file
    if args.check:
        if not path.exists():
            print(f"error: {path} missing (run 'render' first)", file=sys.stderr)
            return 1
        if path.read_text(encoding="utf-8") != text:
            print(f"error: {path} drifted from tasks.json (run 'render')", file=sys.stderr)
            return 1
        print("OK: view in sync")
        return 0
    target = Path(args.out) if args.out else path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")
    print(f"rendered {target}")
    return 0


def cmd_sort(args: argparse.Namespace) -> int:
    project = store.open_project()
    with store.locked(project):
        data = store.load(project)
        before = [t.get("id") for t in data.get("tasks", [])]
        data["tasks"] = ordering.sorted_tasks(data.get("tasks", []))
        store.save(project, data)
        reordered = before != [t.get("id") for t in data["tasks"]]
        store.append_log(project, "sort", "-", identity(args), {"reordered": reordered})
    print("sorted tasks.json" if reordered else "already sorted")
    return 0
