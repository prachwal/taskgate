# taskgate

A task registry that makes "done" mean something. Tasks move through a strict status flow, and the
transitions that matter are gated by evidence: a task enters review only with a green verification, and
closes only with a review from a *different* identity that lists the commands it checked. It ships as a CLI
and as an MCP server, so coding agents (Claude Code, Codex, VS Code Copilot, Cursor, Gemini CLI) and humans
work from the same registry.

- stdlib-only, no runtime dependencies; Python 3.11+; Linux, macOS and Windows
- state is plain files you commit: `tasks.json` (source of truth), an append-only `tasks.log.jsonl` and a
  generated `tasks.md`
- one code path: every MCP tool calls the same CLI command a human would run

## Quick start

```sh
cd your-project
uvx taskgate init
uvx taskgate add --id T-1 --title "Parse the header" --verification-cmd "pytest tests/test_header.py"
uvx taskgate next              # which task may start now
uvx taskgate claim T-1 --by dev
```

Add it to your agent (prints a ready-to-paste block; see [docs/clients.md](docs/clients.md)):

```sh
uvx taskgate config-snippet claude     # also: vscode, codex, cursor, gemini, generic
```

From a checkout instead of PyPI: `uvx --from /path/to/taskgate taskgate ...`, or
`taskgate config-snippet claude --from /path/to/taskgate`.

## The flow

```
draft -> planned -> in_progress -> in_review -> done
                        |  ^           |
                        v  |           +--> in_progress   (review rejected)
                      blocked
any non-terminal status -> cancelled
```

| Rule | What it enforces |
| --- | --- |
| order | `claim` works only on tasks whose predecessors in the registry are `done` or `cancelled` |
| phase gate | a task in a later phase waits until every earlier phase is closed and the registry validates |
| dependencies | `depends_on` tasks must be `done` before the task can start |
| verification | `in_review` and `done` need a green `verification_result`; the tool stamps who recorded it and when |
| review | `done` needs a green `review_result` from the reviewer identity, different from the verifier, listing `checks`, recorded after a delay, in the same call as the closing update |
| fresh evidence | a new verification voids an earlier review; results are never accepted together in one call |
| planning | adding, moving and re-linking tasks is limited to the `planners` identities; started work is never reordered |

Identities (`--by`, or the `TASKGATE_BY` environment variable, default `human`) are *declared by the caller*.
This is a process barrier that keeps roles apart and leaves a trail in the log; it is not authentication.

## Configuration

Optional `taskgate.toml` in the project root; every key has a default
([examples/taskgate.toml](examples/taskgate.toml)).

| Key | Default | Meaning |
| --- | --- | --- |
| `data_dir` | `.taskgate` | where `tasks.json`, `tasks.log.jsonl`, `tasks.md` live |
| `title` | `Tasks` | heading of the Markdown view |
| `id_pattern` | `^[A-Za-z][A-Za-z0-9]*-\d+$` | task id regex; a named group `(?P<phase>\d+)` ties the id to the phase |
| `phase_names` | none | `{0 = "Foundations"}` labels for the view |
| `planners` | `["human"]` | identities allowed to add, move and re-link tasks |
| `reviewer` | `"reviewer"` | identity whose `review_result` closes a task |
| `owners` | any | restrict `owner` values |
| `require_review` | `true` | `false`: `done` needs only a green verification |
| `review_delay_seconds` | `60` | minimum time between verification and review |
| `[quality]` | none | named gates for the `quality_check` tool, each a list of argv arrays |

The project root is `TASKGATE_ROOT` if set, otherwise the nearest ancestor of the working directory that has
`taskgate.toml` or `.taskgate/`.
[examples/embersail.toml](examples/embersail.toml) reproduces a stricter real-world setup (ids `P<phase>-NN`,
architect/human planners) to show the engine is not tied to one convention.

## Commands

`init`, `validate`, `render [--check]`, `next`, `list [--status]`, `claim`, `update`, `add`, `sort`, `move`,
`depends`, `mcp`, `config-snippet`. `taskgate <command> --help` lists the flags.

Recording evidence, in separate calls:

```sh
taskgate update T-1 --verification-result '{"ok": true}' --by dev
taskgate update T-1 --status in_review --by dev
taskgate update T-1 --status done --by reviewer \
  --review-result '{"ok": true, "by": "reviewer", "checks": ["pytest -q"]}'
```

## MCP tools

`task_list`, `task_next`, `task_validate` (read-only, so clients can skip the approval prompt), `task_claim`,
`task_update`, `task_add`, `task_move`, `task_depends`, `task_sort`, `task_render` and `quality_check`.
Tool failures come back as `isError` results rather than protocol errors, so an agent sees the reason.

The server speaks newline-delimited JSON-RPC 2.0 over stdio. Run it with `taskgate mcp` or `taskgate-mcp`.

## Development

```sh
python -m pip install -e ".[dev]"
ruff check . && mypy && pytest
```

## Releasing

Pushing to `main` runs the tests on Linux, macOS and Windows and builds the package. If `version` in
`pyproject.toml` has no `v<version>` tag yet, the workflow publishes to PyPI through trusted publishing and
creates the tag and GitHub release. To release: bump `version` in `pyproject.toml` and
`src/taskgate/__init__.py` (a test keeps them equal), add a changelog entry, merge to `main`.

One-time setup: on PyPI add a (pending) trusted publisher for this repository, workflow `ci.yml`,
environment `pypi`; on GitHub create an environment named `pypi`.

## Status

Alpha. Not included: synchronization with a forge (GitLab/GitHub issues). It originated in the Embersail
project's task tooling.

## License

MIT
