"""CLI entrypoint: ``taskgate`` / ``python -m taskgate``."""

from __future__ import annotations

import argparse
import sys

from . import __version__, clients, model
from .commands.flow import cmd_add, cmd_claim, cmd_list, cmd_next, cmd_update
from .commands.plan import cmd_depends, cmd_move
from .commands.registry import cmd_init, cmd_render, cmd_sort, cmd_validate

BY_HELP = "identity (default TASKGATE_BY env / 'human')"


def _cmd_snippet(args: argparse.Namespace) -> int:
    try:
        print(clients.snippet(args.client, source=args.source, root=args.root), end="")
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return 0


def _cmd_mcp(_args: argparse.Namespace) -> int:
    from .mcp import server  # lazy: the server imports this module's main()

    server.serve()
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Assemble the argparse tree."""
    parser = argparse.ArgumentParser(
        prog="taskgate",
        description="Gated task registry: strict status flow with verification and review evidence.",
    )
    parser.add_argument("--version", action="version", version=f"taskgate {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("init", help="create the registry in the current directory (or TASKGATE_ROOT)")
    p.add_argument("--seed", help="path to seed JSON (tasks array)")
    p.add_argument("--force", action="store_true", help="overwrite existing registry")
    p.add_argument("--by", help=BY_HELP)
    p.set_defaults(func=cmd_init)

    p = sub.add_parser("validate", help="schema + flow-rule validation")
    p.set_defaults(func=cmd_validate)

    p = sub.add_parser("render", help="generate the Markdown view")
    p.add_argument("--check", action="store_true", help="fail when the view drifted from tasks.json")
    p.add_argument("--out", help="alternative output path (ignored with --check)")
    p.set_defaults(func=cmd_render)

    p = sub.add_parser("next", help="show the one task that may start now (queue head)")
    p.add_argument("--owner", help="only tasks unowned or owned by this identity")
    p.set_defaults(func=cmd_next)

    p = sub.add_parser("list", help="list all tasks")
    p.add_argument("--status", choices=model.STATUSES, help="filter by status")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("claim", help="claim a planned task (-> in_progress)")
    p.add_argument("id")
    p.add_argument("--by", help=BY_HELP)
    p.add_argument("--force", action="store_true", help="steal from another owner")
    p.set_defaults(func=cmd_claim)

    p = sub.add_parser("update", help="change status / record verification or review")
    p.add_argument("id")
    p.add_argument("--status", choices=model.STATUSES)
    p.add_argument("--reason", help="required by blocked; recorded for cancelled")
    p.add_argument("--verification-result", help="JSON object, e.g. '{\"ok\": true}'")
    p.add_argument(
        "--review-result",
        help="JSON object from the reviewer, e.g. '{\"ok\": true, \"by\": \"reviewer\", \"checks\": [\"cmd\"]}'",
    )
    p.add_argument("--by", help=BY_HELP)
    p.set_defaults(func=cmd_update)

    p = sub.add_parser("add", help="append a new task to the registry")
    p.add_argument("--id", required=True, help="id matching the configured id_pattern")
    p.add_argument("--title", required=True)
    p.add_argument("--phase", type=int, help="phase (default: from the id's 'phase' group, else 0)")
    p.add_argument("--verification-cmd", required=True, dest="verification_cmd")
    p.add_argument("--spec", help="spec_source anchor (path + section)")
    p.add_argument("--status", default="planned", choices=model.ADD_STATUSES)
    p.add_argument("--owner")
    p.add_argument("--depends", help="comma-separated task ids")
    p.add_argument("--by", help=BY_HELP)
    p.set_defaults(func=cmd_add)

    p = sub.add_parser("sort", help="reset the execution order to phase, then id")
    p.add_argument("--by", help=BY_HELP)
    p.set_defaults(func=cmd_sort)

    p = sub.add_parser("move", help="place a draft/planned task before or after another")
    p.add_argument("id")
    anchor = p.add_mutually_exclusive_group(required=True)
    anchor.add_argument("--before", metavar="ID", help="place directly before this task")
    anchor.add_argument("--after", metavar="ID", help="place directly after this task")
    p.add_argument("--by", help=BY_HELP)
    p.set_defaults(func=cmd_move)

    p = sub.add_parser("depends", help="change the dependencies of a draft/planned task")
    p.add_argument("id")
    p.add_argument("--set", help="comma-separated ids replacing the dependencies ('' clears)")
    p.add_argument("--add", help="comma-separated ids to add")
    p.add_argument("--remove", help="comma-separated ids to remove")
    p.add_argument("--by", help=BY_HELP)
    p.set_defaults(func=cmd_depends)

    p = sub.add_parser("mcp", help="start the MCP stdio server (JSON-RPC 2.0, newline-delimited)")
    p.set_defaults(func=_cmd_mcp)

    p = sub.add_parser("config-snippet", help="print MCP configuration for a client")
    p.add_argument("client", choices=list(clients.CLIENTS), help="; ".join(f"{k}: {v}" for k, v in clients.CLIENTS.items()))
    p.add_argument("--from", dest="source", help="uvx source (path, git URL or version spec); default: PyPI")
    p.add_argument("--root", help="absolute project root, written as TASKGATE_ROOT")
    p.set_defaults(func=_cmd_snippet)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Program entry: dispatch commands, return the exit code."""
    args = build_parser().parse_args(argv)
    code: int = args.func(args)
    return code


def run() -> None:
    """Console-script entry point."""
    sys.exit(main())
