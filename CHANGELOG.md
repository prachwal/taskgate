# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/).

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
