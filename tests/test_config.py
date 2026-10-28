from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
from conftest import Run

from taskgate import config
from taskgate.model import validate

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


def test_defaults_without_a_file(tmp_path: Path) -> None:
    cfg = config.load(tmp_path)
    assert cfg.data_dir == ".taskgate" and cfg.planners == ("human",) and cfg.require_review


def test_unknown_key_is_rejected() -> None:
    with pytest.raises(SystemExit, match="unknown keys"):
        config.parse({"planer": ["x"]})


@pytest.mark.parametrize(
    "raw",
    [
        {"id_pattern": "("},
        {"planners": "human"},
        {"require_review": "yes"},
        {"review_delay_seconds": -1},
        {"phase_names": {"x": "bad"}},
        {"quality": {"t": ["pytest"]}},
    ],
)
def test_invalid_values_are_rejected(raw: dict[str, object]) -> None:
    with pytest.raises(SystemExit):
        config.parse(raw)


def test_find_root_walks_up(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TASKGATE_ROOT", raising=False)
    (tmp_path / "taskgate.toml").write_text("", encoding="utf-8")
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    assert config.find_root(nested) == tmp_path.resolve()


def test_find_root_env_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TASKGATE_ROOT", str(tmp_path))
    assert config.find_root(Path("/")) == tmp_path.resolve()


def test_find_root_fails_clearly(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TASKGATE_ROOT", raising=False)
    with pytest.raises(SystemExit, match="no taskgate project"):
        config.find_root(tmp_path)


def test_example_configs_parse() -> None:
    for name in ("taskgate.toml", "embersail.toml"):
        config.parse(tomllib.loads((EXAMPLES / name).read_text(encoding="utf-8")))


def test_embersail_profile_reproduces_its_rules(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from taskgate import cli

    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("TASKGATE_ROOT", raising=False)
    (tmp_path / "taskgate.toml").write_text((EXAMPLES / "embersail.toml").read_text(encoding="utf-8"), encoding="utf-8")
    assert cli.main(["init"]) == 0
    add = ["add", "--title", "x", "--verification-cmd", "true", "--by", "architect"]
    assert cli.main([*add, "--id", "P2-01"]) == 0  # phase taken from the id
    assert cli.main([*add, "--id", "T-1"]) == 1  # wrong id shape
    assert cli.main(["add", "--id", "P2-02", "--title", "x", "--verification-cmd", "true", "--by", "human", "--phase", "3"]) == 1
    capsys.readouterr()
    assert (tmp_path / "docs" / "tasks" / "tasks.json").is_file()
    cfg = config.load(tmp_path)
    data = {"version": 1, "tasks": [{"id": "P2-01", "title": "t", "status": "planned", "verification_cmd": "c", "phase": 4}]}
    assert any("does not match the id" in e for e in validate(data, cfg))


def test_phase_names_in_view(tg: Run, project: Path) -> None:
    (project / "taskgate.toml").write_text('[phase_names]\n0 = "Foundations"\n', encoding="utf-8")
    tg("init")
    tg("add", "--id", "T-1", "--title", "x", "--verification-cmd", "true")
    assert "## Foundations (0/1 done)" in (project / ".taskgate" / "tasks.md").read_text(encoding="utf-8")
