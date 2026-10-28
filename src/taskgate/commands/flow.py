"""Task flow commands: next, list, claim, update, add."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from typing import Any

from .. import model, ordering, store
from ..config import Config
from .common import VERIFICATION_STATUSES, find, identity


def cmd_next(args: argparse.Namespace) -> int:
    project = store.open_project()
    data = store.load(project)
    head = ordering.queue_head(data.get("tasks", []))
    if head is None:
        print("no open tasks (every task is done or cancelled)")
        return 2
    if head.get("status") != "planned":
        print(f"nothing to claim: {head['id']} is next in order and is {head.get('status')!r}")
        return 2
    blockers = ordering.claim_blockers(data, head, project.config)
    if blockers:
        print(f"{head['id']} is next in order but cannot start:", file=sys.stderr)
        for reason in blockers:
            print(f"  - {reason}", file=sys.stderr)
        return 2
    if args.owner and head.get("owner") not in (None, args.owner):
        print(f"nothing to claim: {head['id']} is owned by {head['owner']!r}")
        return 2
    owner = head.get("owner") or "unowned"
    print(f"{head['id']}  [{owner}]  {head['title']}  // verify: {head.get('verification_cmd')}")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    project = store.open_project()
    rows = store.load(project).get("tasks", [])
    for t in rows:
        if args.status and t.get("status") != args.status:
            continue
        info = f"  // blocked: {t.get('blocked_reason')}" if t.get("status") == "blocked" else ""
        if t.get("depends_on"):
            info += f"  <- {','.join(t['depends_on'])}"
        print(f"{t['id']}  {t.get('status'):12}  {t.get('owner') or '-':12}  {t.get('title')}{info}")
    print(f"-- {len(rows)} task(s)")
    return 0


def cmd_claim(args: argparse.Namespace) -> int:
    project = store.open_project()
    by = identity(args)
    with store.locked(project):
        data = store.load(project)
        task, found = find(data, args.id)
        if not found:
            print(f"error: unknown task {args.id}", file=sys.stderr)
            return 1
        current = task.get("status")
        if current != "planned":
            print(f"error: {args.id} is {current!r}, claim requires 'planned'", file=sys.stderr)
            return 1
        blockers = ordering.claim_blockers(data, task, project.config)
        if blockers:
            print(f"error: {args.id} cannot start:", file=sys.stderr)
            for reason in blockers:
                print(f"  - {reason}", file=sys.stderr)
            return 1
        if task.get("owner") and task["owner"] != by and not args.force:
            print(f"error: {args.id} already owned by {task['owner']!r} (--force to steal)", file=sys.stderr)
            return 1
        task.update({"status": "in_progress", "owner": by, "started": store.now()})
        store.save(project, data)
        store.append_log(project, "claim", args.id, by, {"status": "in_progress"})
    print(f"{args.id} claimed by {by} -> in_progress")
    return 0


def _parse_result(raw: str, flag: str) -> dict[str, Any] | None:
    """Parse a ``--*-result`` JSON object; ``None`` means the payload was refused."""
    try:
        result = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"error: {flag} is not valid JSON: {exc}", file=sys.stderr)
        return None
    if not isinstance(result, dict):
        print(f"error: {flag} must be a JSON object", file=sys.stderr)
        return None
    return result


def _parse_instant(value: Any) -> datetime | None:
    """Parse a stored timestamp as a timezone-aware instant (``Z`` or offset)."""
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else None


def _review_problem(task: dict[str, Any], review: dict[str, Any], by: str, config: Config) -> str | None:
    """Check the review write preconditions, in the order the contract fixes them."""
    reviewer = config.reviewer
    if by != reviewer or review.get("by") != reviewer:
        return f"review_result.by and caller identity must both be {reviewer!r}"
    verification = task.get("verification_result")
    if not isinstance(verification, dict) or not model.is_green(verification):
        return "recording review_result requires a green verification_result"
    verifier = verification.get("by")
    if not isinstance(verifier, str) or not verifier.strip():
        return "verification_result.by is required; record fresh verification before review"
    if verifier == reviewer:
        return "reviewer must differ from verification_result.by"
    checks = review.get("checks")
    if not isinstance(checks, list) or not checks or not all(isinstance(c, str) and c.strip() for c in checks):
        return "review_result.checks must be a non-empty list of non-blank command strings"
    verified_at = _parse_instant(verification.get("at"))
    if verified_at is None:
        return (
            "verification_result.at must be a timezone-aware ISO-8601 datetime; "
            "record fresh verification before review"
        )
    current = _parse_instant(store.now())
    elapsed = None if current is None else (current - verified_at).total_seconds()
    if elapsed is None or elapsed < config.review_delay_seconds:
        return f"review_result requires at least {config.review_delay_seconds} seconds after verification_result.at"
    return None


def cmd_update(args: argparse.Namespace) -> int:
    project = store.open_project()
    config = project.config
    by = identity(args)
    with store.locked(project):
        data = store.load(project)
        task, found = find(data, args.id)
        if not found:
            print(f"error: unknown task {args.id}", file=sys.stderr)
            return 1
        if args.verification_result is not None and args.review_result is not None:
            print(
                "error: verification_result and review_result must be recorded in separate update calls",
                file=sys.stderr,
            )
            return 1
        current = task.get("status") or "draft"
        if current in model.TERMINAL and (
            args.verification_result is not None or args.review_result is not None or args.status is not None
        ):
            print("error: terminal tasks cannot receive result writes or be closed again", file=sys.stderr)
            return 1
        verification: dict[str, Any] | None = None
        if args.verification_result is not None:
            verification = _parse_result(args.verification_result, "--verification-result")
            if verification is None:
                return 1
            claimed_by = verification.get("by")
            if claimed_by is not None and claimed_by != by:
                print("error: verification_result.by must match the caller identity", file=sys.stderr)
                return 1
            verification["by"] = by
            # tool-owned timestamp: a caller-supplied 'at' cannot backdate evidence
            verification["at"] = store.now()
            verification.setdefault("cmd", task.get("verification_cmd"))
        review: dict[str, Any] | None = None
        if args.review_result is not None:
            review = _parse_result(args.review_result, "--review-result")
            if review is None:
                return 1
            problem = _review_problem(task, review, by, config)
            if problem is not None:
                print(f"error: {problem}", file=sys.stderr)
                return 1
            review["at"] = store.now()
        if review is not None and current != "in_review":
            print("error: review_result can only be recorded while the task is 'in_review'", file=sys.stderr)
            return 1
        if args.status == "done" and review is None and config.require_review:
            print("error: --status done requires a fresh --review-result in the same update", file=sys.stderr)
            return 1
        detail: dict[str, Any] = {}
        if verification is not None:
            # a fresh verification voids the earlier approval
            task.pop("review_result", None)
            task["verification_result"] = verification
            detail["verification_result"] = True
        if args.status == "in_progress" and current != args.status:
            task.pop("review_result", None)
        if review is not None:
            task["review_result"] = review
            detail["review_result"] = True
        if args.status is not None:
            if current != args.status and not model.can_transition(current, args.status):
                allowed = sorted(model.TRANSITIONS.get(current, frozenset()))
                print(
                    f"error: {args.id}: {current!r} -> {args.status!r} not allowed (allowed: {allowed})",
                    file=sys.stderr,
                )
                return 1
            if current == "planned" and args.status == "in_progress":
                print(
                    f"error: {args.id}: start work with 'claim' "
                    "(it enforces order, dependencies and the phase gate)",
                    file=sys.stderr,
                )
                return 1
            if args.status == "blocked":
                reason = args.reason or task.get("blocked_reason")
                if not reason:
                    print("error: --status blocked requires --reason", file=sys.stderr)
                    return 1
                task["blocked_reason"] = reason
                detail["blocked_reason"] = reason
            elif current == "blocked":
                task.pop("blocked_reason", None)
                detail["blocked_reason"] = None
            if args.status == "in_progress" and not task.get("started"):
                task["started"] = store.now()
            if args.status in model.TERMINAL:
                task["finished"] = store.now()
                if args.status == "cancelled" and args.reason:
                    task.setdefault("notes", []).append(
                        {"at": store.now(), "by": by, "text": f"cancelled: {args.reason}"}
                    )
            task["status"] = args.status
            detail["status"] = args.status
        if args.status in VERIFICATION_STATUSES and not model.is_green(task.get("verification_result")):
            print(
                f"error: --status {args.status} requires a green verification_result "
                "(pass --verification-result '{\"ok\": true, ...}')",
                file=sys.stderr,
            )
            return 1
        if args.status == "done" and config.require_review and not model.is_review(
            task.get("review_result"), config.reviewer
        ):
            print(
                "error: --status done requires a green review_result with the reviewer identity "
                f"(pass --review-result '{{\"ok\": true, \"by\": \"{config.reviewer}\", \"checks\": [...]}}')",
                file=sys.stderr,
            )
            return 1
        store.save(project, data)
        store.append_log(project, "update", args.id, by, detail or {"no-op": True})
    print(f"{args.id} updated ({', '.join(f'{k}={v!r}' for k, v in detail.items()) or 'no-op'})")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    project = store.open_project()
    config = project.config
    by = identity(args)
    if by not in config.planners:
        print(
            f"error: only {', '.join(config.planners)} may add tasks (got {by!r}); pass --by with a planner identity",
            file=sys.stderr,
        )
        return 1
    match = config.id_regex.fullmatch(args.id)
    phase = args.phase
    if phase is None:
        phase = int(match.group("phase")) if match and "phase" in match.groupdict() and match.group("phase") else 0
    task: dict[str, Any] = {
        "id": args.id,
        "title": args.title,
        "phase": phase,
        "status": args.status,
        "verification_cmd": args.verification_cmd,
    }
    if args.spec:
        task["spec_source"] = args.spec
    if args.owner:
        task["owner"] = args.owner
    if args.depends:
        task["depends_on"] = [d for d in args.depends.split(",") if d]
    with store.locked(project):
        data = store.load(project)
        if find(data, args.id)[1]:
            print(f"error: task {args.id} already exists", file=sys.stderr)
            return 1
        phase_now = ordering.current_phase(data["tasks"])
        if phase < phase_now:
            print(
                f"error: phase {phase} is already closed (current phase is {phase_now}); "
                f"add the task to phase {phase_now} or later",
                file=sys.stderr,
            )
            return 1
        # appended after the last task of its phase; 'move' places it elsewhere
        position = ordering.insert_position(data["tasks"], phase)
        data["tasks"] = [*data["tasks"][:position], task, *data["tasks"][position:]]
        errors = model.validate(data, config)
        if errors:
            for error in errors:
                print(f"ERROR: {error}", file=sys.stderr)
            return 1
        task["created"] = store.now()
        store.save(project, data)
        store.append_log(project, "add", args.id, by, {"status": task["status"]})
    print(f"{args.id} added ({task['status']})")
    return 0
