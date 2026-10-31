# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

## [0.3.0] - 2026-10-31

### Added
- `edit` / `task_edit`: change the title, `spec_source` or `verification_cmd` of a draft/planned task (planners only).
- `note` / `task_note`: append a timestamped note to a task in any status.
- `log` / `task_log`: read `tasks.log.jsonl`, filtered by task (subtasks included), identity or count; `--json`.
- `doctor` / `task_doctor`: check the project root, configuration, registry, view drift and log.
- `--json` for `list` and `next` (and `json: true` on `task_list` and `task_next`).
- Returning a task from review (`in_review` to `in_progress`) with `--reason` records the reason as a note.

### Changed
- MCP tools reject undeclared and missing required arguments with the allowed names. Before, an argument with a
  wrong name (for example `spec_source` instead of `spec`) was silently dropped.
- `update` that changes nothing now fails with a hint instead of reporting a `no-op` and writing a log entry.

## [0.2.0] - 2026-10-29

### Added
- Subtasks: `add --parent` creates `<parent>.<n>` (one level, phase from the parent). Subtasks start only while the
  parent is `in_progress`; `next` hands out the first open subtask; a parent cannot enter `in_review`, `done` or
  `cancelled` while a subtask is open. The Markdown view nests subtasks and shows their progress.
- Profiles: `[profiles.<name>]` in `taskgate.toml` overrides `require_review`, `reviewer`, `review_delay_seconds` and
  the quality `gates` per task, so a documentation change can skip the review or use a cheaper reviewer. A task takes
  its own profile, else its parent's, else the project-wide settings.
- `show` / `task_show`: a task with its effective closing policy and subtasks. `profile` / `task_profile`: set or
  clear the profile of a draft/planned task (planners only). `quality_check` accepts `task` to run just that task's
  gates. `next` states how the task closes when it is a subtask or has a profile.

### Changed
- The review requirement, reviewer identity and delay are resolved per task. Registries and configurations without
  `parent`, `profile` or `[profiles]` behave exactly as in 0.1.0.

## [0.1.0] - 2026-10-28

### Added
- Gated task registry: seven statuses with strict transitions, execution order, phase gate and dependencies.
- Evidence gates: a task enters `in_review` only with a green verification and closes only with a review from a
  different identity, listing the commands it checked, after a configurable delay.
- Append-only mutation log, generated Markdown view with drift check, atomic and lock-serialized writes
  (Linux, macOS, Windows).
- MCP stdio server with 11 tools; read-only tools carry `readOnlyHint`.
- `taskgate.toml` configuration: id pattern, phases, planners, reviewer, owners, review requirement and delay,
  quality gates.
- `taskgate config-snippet` for Claude Code, VS Code (Copilot), Codex, Cursor and Gemini CLI.
- `examples/embersail.toml` profile reproducing the Embersail task flow.

### Not included
- Forge synchronization (the Embersail GitLab sync was not carried over).
