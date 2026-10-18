"""Tests for the one-off BAU projects.yaml import, against a fake ATC (no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from atc.import_projects import ImportResult, import_projects, main, parse_projects_yaml


class FakeAtcClient:
    """Stands in for AtcHttp: PUT /api/projects/{IDENT} returns 404 for unknown identifiers."""

    def __init__(self) -> None:
        self.known: set[str] = set()
        self.project_puts: dict[str, dict] = {}
        self.status_override: int | None = None

    def put(self, path: str, body: dict) -> tuple[int, dict]:
        ident = path.removeprefix("/api/projects/")
        if self.status_override:
            return self.status_override, {}
        if ident not in self.known:
            return 404, {"detail": "unknown project"}
        self.project_puts[ident] = body
        return 200, {"identifier": ident, **body}

    def get(self, path: str, **params):  # pragma: no cover - the import never reads
        raise AssertionError("the import must not GET")


@pytest.fixture
def fake_atc() -> FakeAtcClient:
    return FakeAtcClient()


def write_yaml(tmp_path: Path) -> Path:
    y = tmp_path / "projects.yaml"
    y.write_text(
        'projects:\n  HOME: {repo: nakomis/home-infra, deploys: true, deploy_action: "Run it"}\n'
        '  PROJ: {repo: null, deploys: false, deploy_action: ""}\n  GONE: {repo: a/b, deploys: false}\n'
    )
    return y


def test_import_sets_metadata_and_enables_bau(fake_atc, tmp_path):
    fake_atc.known = {"HOME", "PROJ"}
    r = import_projects(fake_atc, parse_projects_yaml(write_yaml(tmp_path)))
    assert isinstance(r, ImportResult)
    assert (sorted(r.updated), r.unknown) == (["HOME", "PROJ"], ["GONE"])
    assert fake_atc.project_puts["HOME"] == {
        "repo": "nakomis/home-infra",
        "deploys": True,
        "deploy_action": "Run it",
        "bau_enabled": True,
    }
    assert fake_atc.project_puts["PROJ"]["repo"] is None


def test_missing_fields_get_defaults(fake_atc, tmp_path):
    fake_atc.known = {"GONE"}
    import_projects(fake_atc, parse_projects_yaml(write_yaml(tmp_path)))
    assert fake_atc.project_puts["GONE"] == {
        "repo": "a/b",
        "deploys": False,
        "deploy_action": "",
        "bau_enabled": True,
    }


def test_unexpected_status_raises(fake_atc, tmp_path):
    fake_atc.status_override = 500
    with pytest.raises(RuntimeError, match="HOME.*500"):
        import_projects(fake_atc, parse_projects_yaml(write_yaml(tmp_path)))


def test_real_bau_file_parses(tmp_path):
    bau = Path.home() / "repos/nakomis/bau/config/projects.yaml"
    if not bau.exists():
        pytest.skip("BAU checkout not present")
    projects = parse_projects_yaml(bau)
    assert len(projects) >= 30
    assert projects["PROJ"]["repo"] is None


def test_parse_rejects_file_without_projects(tmp_path):
    y = tmp_path / "x.yaml"
    y.write_text("other: 1\n")
    with pytest.raises(ValueError):
        parse_projects_yaml(y)


def test_main_dry_run_makes_no_calls(fake_atc, tmp_path, capsys):
    fake_atc.known = {"HOME"}
    rc = main([str(write_yaml(tmp_path)), "--dry-run"], client_factory=lambda **_: fake_atc)
    assert rc == 0 and fake_atc.project_puts == {}
    assert "HOME" in capsys.readouterr().out


def test_main_reports_unknown_and_exits_nonzero(fake_atc, tmp_path, capsys):
    fake_atc.known = {"HOME", "PROJ"}
    rc = main([str(write_yaml(tmp_path))], client_factory=lambda **_: fake_atc)
    out = capsys.readouterr().out
    assert rc == 1 and "GONE" in out and sorted(fake_atc.project_puts) == ["HOME", "PROJ"]


def test_main_all_known_exits_zero(fake_atc, tmp_path):
    fake_atc.known = {"HOME", "PROJ", "GONE"}
    assert main([str(write_yaml(tmp_path))], client_factory=lambda **_: fake_atc) == 0
