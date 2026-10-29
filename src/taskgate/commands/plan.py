"""Planning commands: move (execution order) and depends (dependencies)."""

from __future__ import annotations

import argparse
import sys
from typing import Any

from .. import model, ordering, store
from ..config import DEFAULT_PROFILE, Config
from .common import find, identity


def _planner(args: argparse.Namespace, config: Config) -> str | None:
    """The caller identity when it may plan, otherwise ``None`` after printing the refusal."""
    by = identity(args)
    if by not in config.planners:
        print(
            f"error: only {', '.join(config.planners)} may change the plan (got {by!r}); "
            f"pass --by with a planner identity",
            file=sys.stderr,
        )
        return None
    return by


def _valid(data: dict[str, Any], config: Config) -> bool:
    errors = model.validate(data, config)
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    return not errors


def cmd_move(args: argparse.Namespace) -> int:
    project = store.open_project()
    by = _planner(args, project.config)
    if by is None:
        return 1
    anchor = args.before or args.after
    with store.locked(project):
        data = store.load(project)
        blockers = ordering.move_blockers(data.get("tasks", []), args.id, anchor, after=bool(args.after))
        if blockers:
            for reason in blockers:
                print(f"error: {reason}", file=sys.stderr)
            return 1
        data["tasks"] = ordering.moved(data["tasks"], args.id, anchor, after=bool(args.after))
        if not _valid(data, project.config):
            return 1
        place = "after" if args.after else "before"
        store.save(project, data)
        store.append_log(project, "move", args.id, by, {place: anchor})
    print(f"{args.id} moved {place} {anchor}")
    return 0


def _ids(raw: str | None) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()] if raw else []


def cmd_depends(args: argparse.Namespace) -> int:
    project = store.open_project()
    by = _planner(args, project.config)
    if by is None:
        return 1
    if args.set is None and not args.add and not args.remove:
        print("error: pass --set, --add or --remove", file=sys.stderr)
        return 1
    if args.set is not None and (args.add or args.remove):
        print("error: --set cannot be combined with --add or --remove", file=sys.stderr)
        return 1
    with store.locked(project):
        data = store.load(project)
        task, found = find(data, args.id)
        if not found:
            print(f"error: unknown task {args.id}", file=sys.stderr)
            return 1
        if task.get("status") not in ordering.MOVABLE:
            print(
                f"error: {args.id} is {task.get('status')!r}; dependencies can only change "
                "while a task is draft or planned",
                file=sys.stderr,
            )
            return 1
        current = list(task.get("depends_on") or [])
        wanted = _ids(args.set) if args.set is not None else [*current, *_ids(args.add)]
        removed = set(_ids(args.remove))
        result = list(dict.fromkeys(dep for dep in wanted if dep not in removed))
        if args.id in result:
            print(f"error: {args.id} cannot depend on itself", file=sys.stderr)
            return 1
        if result:
            task["depends_on"] = result
        else:
            task.pop("depends_on", None)
        if not _valid(data, project.config):
            return 1
        store.save(project, data)
        store.append_log(project, "depends", args.id, by, {"depends_on": result})
    print(f"{args.id} depends on {', '.join(result) if result else 'nothing'}")
    return 0


def cmd_profile(args: argparse.Namespace) -> int:
    """Set or clear the review/verification profile of a task that has not started."""
    project = store.open_project()
    by = _planner(args, project.config)
    if by is None:
        return 1
    if (args.name is None) == (not args.clear):
        print("error: pass exactly one of a profile name or --clear", file=sys.stderr)
        return 1
    config = project.config
    if args.name and args.name != DEFAULT_PROFILE and args.name not in config.profiles:
        print(f"error: unknown profile {args.name!r} (known: {', '.join(sorted(config.profiles)) or 'none'})", file=sys.stderr)
        return 1
    with store.locked(project):
        data = store.load(project)
        task, found = find(data, args.id)
        if not found:
            print(f"error: unknown task {args.id}", file=sys.stderr)
            return 1
        if task.get("status") not in ordering.MOVABLE:
            print(
                f"error: {args.id} is {task.get('status')!r}; the profile can only change while a task is draft or "
                "planned (changing it later would change how finished work is judged)",
                file=sys.stderr,
            )
            return 1
        if args.clear:
            task.pop("profile", None)
        else:
            task["profile"] = args.name
        if not _valid(data, config):
            return 1
        store.save(project, data)
        store.append_log(project, "profile", args.id, by, {"profile": task.get("profile")})
    print(f"{args.id} profile: {task.get('profile') or 'inherited/default'}")
    return 0
