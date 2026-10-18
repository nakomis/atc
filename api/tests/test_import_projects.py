"""Tests for the one-off BAU projects.yaml import, against a fake ATC (no network)."""

from __future__ import annotations

from pathlib import Path

import pytest

from atc.import_projects import DEFAULT_META, ImportResult, import_projects, main, parse_projects_yaml


class FakeAtcClient:
    """Stands in for AtcHttp: /api/projects/{IDENT} answers 404 for unknown identifiers."""

    def __init__(self) -> None:
        self.known: set[str] = set()
        self.meta: dict[str, dict] = {}  # ATC's current metadata, defaults unless a test sets it
        self.project_puts: dict[str, dict] = {}
        self.status_override: int | None = None

    def get_status(self, path: str) -> tuple[int, dict]:
        ident = path.removeprefix("/api/projects/")
        if self.status_override:
            return self.status_override, {}
        if ident not in self.known:
            return 404, {"detail": "unknown project"}
        return 200, {"identifier": ident, **DEFAULT_META, **self.meta.get(ident, {})}

    def put(self, path: str, body: dict) -> tuple[int, dict]:
        ident = path.removeprefix("/api/projects/")
        if self.status_override:
            return self.status_override, {}
        if ident not in self.known:
            return 404, {"detail": "unknown project"}
        self.project_puts[ident] = body
        self.meta[ident] = {**self.meta.get(ident, {}), **body}
        return 200, {"identifier": ident, **self.meta[ident]}

    def get(self, path: str, **params):  # pragma: no cover - the import reads with get_status
        raise AssertionError("the import must use get_status")


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


def test_rerun_fills_only_missing_fields_and_keeps_atc_edits(fake_atc, tmp_path):  # ruling
    fake_atc.known = {"HOME", "PROJ", "GONE"}
    fake_atc.meta = {
        # Martin turned BAU off and changed the action in ATC, but never set a repo.
        "HOME": {"repo": None, "deploys": False, "deploy_action": "Ship it", "bau_enabled": False},
        # Fully edited in ATC: nothing to fill.
        "GONE": {"repo": "x/y", "deploys": True, "deploy_action": "", "bau_enabled": True},
    }
    r = import_projects(fake_atc, parse_projects_yaml(write_yaml(tmp_path)))
    assert fake_atc.project_puts["HOME"] == {"repo": "nakomis/home-infra"}
    assert (
        fake_atc.meta["HOME"]["bau_enabled"] is False and fake_atc.meta["HOME"]["deploy_action"] == "Ship it"
    )
    assert "GONE" not in fake_atc.project_puts and fake_atc.meta["GONE"]["repo"] == "x/y"
    assert fake_atc.project_puts["PROJ"]["bau_enabled"] is True  # untouched in ATC: seeded in full
    assert (sorted(r.updated), r.unchanged, r.unknown) == (["HOME", "PROJ"], ["GONE"], [])
    again = import_projects(fake_atc, parse_projects_yaml(write_yaml(tmp_path)))
    assert (again.updated, sorted(again.unchanged)) == ([], ["GONE", "HOME", "PROJ"])


def test_overwrite_replaces_atc_edits(fake_atc, tmp_path, capsys):
    fake_atc.known = {"HOME", "PROJ", "GONE"}
    fake_atc.meta = {"HOME": {"repo": "x/y", "deploys": False, "deploy_action": "", "bau_enabled": False}}
    rc = main([str(write_yaml(tmp_path)), "--overwrite"], client_factory=lambda **_: fake_atc)
    assert rc == 0
    assert fake_atc.project_puts["HOME"] == {
        "repo": "nakomis/home-infra",
        "deploys": True,
        "deploy_action": "Run it",
        "bau_enabled": True,
    }


def test_main_reports_projects_left_alone(fake_atc, tmp_path, capsys):
    fake_atc.known = {"HOME", "PROJ", "GONE"}
    assert main([str(write_yaml(tmp_path))], client_factory=lambda **_: fake_atc) == 0
    capsys.readouterr()
    assert main([str(write_yaml(tmp_path))], client_factory=lambda **_: fake_atc) == 0
    assert "left alone (3)" in capsys.readouterr().out


def test_unexpected_put_status_raises(fake_atc, tmp_path):
    fake_atc.known = {"HOME", "PROJ", "GONE"}
    fake_atc.put = lambda path, body: (500, {})
    with pytest.raises(RuntimeError, match="PUT .*HOME.*500"):
        import_projects(fake_atc, parse_projects_yaml(write_yaml(tmp_path)))


def test_import_uses_the_client_defaults():
    from atc import client
    from atc import import_projects as module

    assert (module.DEFAULT_URL, module.DEFAULT_CERT, module.DEFAULT_KEY) == (
        client.DEFAULT_URL,
        client.DEFAULT_CERT,
        client.DEFAULT_KEY,
    )


def test_client_get_status_does_not_raise():
    import httpx

    from atc.client import AtcHttp

    def handle(request):
        if request.url.path.endswith("/NOPE"):
            return httpx.Response(404, text="not json")
        return httpx.Response(200, json={"identifier": "HOME"})

    atc = AtcHttp("https://atc.test", transport=httpx.MockTransport(handle))
    assert atc.get_status("/api/projects/HOME") == (200, {"identifier": "HOME"})
    assert atc.get_status("/api/projects/NOPE") == (404, "not json")
