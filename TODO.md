# TODO

Ideas for the next editions, roughly by value. These are candidates, not commitments. Items marked **known gap**
describe something the current version does not do or has not verified.

## Next (0.4)

- [ ] **Forge sync, generalized.** Publish tasks as GitLab/GitHub issues (labels per status, milestones per phase).
      The Embersail version exists (`tools/tasks/gitlab_sync.py`) but hardcodes phases 0-5 and Polish text; it needs
      configurable labels and milestones and should live as an optional integration, not in the core.
      **Known gap:** not carried over in 0.1.
- [ ] **Verify the client config formats.** `config-snippet` output for Claude Code, VS Code, Codex, Cursor and
      Gemini CLI was written from memory of their documentation. Check each against the current docs and a real
      client; add OpenCode and other clients once confirmed. **Known gap.**

## Evidence and trust

- [ ] **Stronger identities.** Identities are declared (`--by`), so the reviewer gate is a process barrier, not
      authentication. Options: sign results with a per-role key (HMAC) kept outside the repo, or require a git
      commit or CI run reference in `checks`. Decide how much is worth the setup cost.
- [ ] **Recorded evidence, not just a flag.** Let `verification_result` carry the command output (truncated) and the
      exit code, and optionally run `verification_cmd` itself (`taskgate verify <id>`), so "green" is produced by the
      tool rather than reported by the caller.
- [ ] **Reopen.** A controlled way to reopen a `done` task (new task linked to the old one, or a `reopened` event)
      instead of the current "terminal tasks are closed".

## Robustness

- [ ] **Concurrency test with real processes.** The lock is covered by the single-process suite and by CI on three
      operating systems, but no test hammers `claim`/`update` from several processes at once. **Known gap.**
- [ ] **Git worktrees.** When run from a linked worktree, decide whether the registry belongs to the worktree or to
      the main checkout (`tasks-toolkit` uses the main checkout). Today it follows the current directory.
- [ ] **Registry versioning.** `version: 1` is validated but there is no migration path; add `taskgate migrate` before
      the schema changes.
- [ ] **Importer for the Embersail registry.** Read `docs/tasks/tasks.json` as is (profile `examples/embersail.toml`
      already matches) and a documented switch-over for Embersail to this package.
- [ ] **Larger registries.** `validate` and `claim` re-read and re-check the whole file on every call; measure at a
      few thousand tasks before optimizing.

## Docs and release

- [ ] **Trusted publishing.** Releases currently use the `PYPI_API_TOKEN` secret. Switch to a trusted publisher
      (OIDC) and drop the secret; narrow any remaining token to this project.
- [ ] **Changelog-driven release notes.** Use the CHANGELOG section as the GitHub release body instead of
      `--generate-notes`.
- [ ] **Worked example.** A short end-to-end guide for two agents (implementer and reviewer) with their MCP
      configurations side by side.
- [ ] **Python 3.12+ typing pass.** Keep `mypy --strict` clean on newer interpreters as they are added to the matrix.
