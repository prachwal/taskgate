"""Adapters to the outside world: the CLI and subprocesses.

Tool modules call these through the module (``bridge.run_cli(...)``), so tests
can replace one function here and every tool sees it.
"""

from __future__ import annotations

import contextlib
import io
import subprocess

from .. import config as config_mod
from ..cli import main as cli_main

PROCESS_TIMEOUT_SECONDS = 1200


def run_cli(argv: list[str]) -> str:
    """Run a CLI command capturing stdout/stderr; raise on non-zero exit."""
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = cli_main(argv)
    output = out.getvalue().strip()
    if code != 0:
        raise RuntimeError(err.getvalue().strip() or output or f"exit code {code}")
    return output or "ok"


def run_process(command: list[str]) -> tuple[int, str]:
    """Run a quality-gate command in the project root and capture its (tail of) output."""
    root = config_mod.find_root()
    try:
        completed = subprocess.run(
            command, cwd=root, capture_output=True, text=True, check=False, timeout=PROCESS_TIMEOUT_SECONDS
        )
    except subprocess.TimeoutExpired as exc:
        return 124, f"timeout: {' '.join(command)} ({exc.timeout}s)"
    except OSError as exc:
        return 127, f"cannot run {' '.join(command)}: {exc}"
    output = "\n".join(part.strip() for part in (completed.stdout, completed.stderr) if part.strip())
    return completed.returncode, output[-4000:]
