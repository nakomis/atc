"""One-off import of BAU's config/projects.yaml into ATC's project metadata.

Run at go-live: `atc-import-projects ~/repos/nakomis/bau/config/projects.yaml`. Every identifier must
land in `updated`; anything in `unknown` has no Plane project and needs looking at.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

if TYPE_CHECKING:  # pragma: no cover
    from atc.client import AtcHttp

DEFAULT_URL = "https://atc.plane.home.nakomis.com"
DEFAULT_CERT = Path("~/.config/nakomis/client.crt")
DEFAULT_KEY = Path("~/.config/nakomis/client.key")


@dataclass
class ImportResult:
    updated: list[str] = field(default_factory=list)
    unknown: list[str] = field(default_factory=list)


def parse_projects_yaml(path: Path) -> dict[str, dict]:
    """The `projects:` mapping of BAU's file (identifier -> settings)."""
    data = yaml.safe_load(Path(path).read_text())
    projects = data.get("projects") if isinstance(data, dict) else None
    if not isinstance(projects, dict):
        raise ValueError(f"{path}: no `projects:` mapping")
    return {str(k): (v or {}) for k, v in projects.items()}


def project_body(entry: dict) -> dict[str, Any]:
    return {
        "repo": entry.get("repo"),
        "deploys": bool(entry.get("deploys", False)),
        "deploy_action": entry.get("deploy_action") or "",
        "bau_enabled": True,
    }


def import_projects(atc: AtcHttp, projects: dict[str, dict]) -> ImportResult:
    """PUT each project's metadata; a 404 means ATC (Plane) has no such identifier."""
    result = ImportResult()
    for ident, entry in projects.items():
        status, _ = atc.put(f"/api/projects/{ident}", project_body(entry))
        if status == 404:
            result.unknown.append(ident)
        elif 200 <= status < 300:
            result.updated.append(ident)
        else:
            raise RuntimeError(f"PUT /api/projects/{ident} returned {status}")
    return result


def _default_client(**kwargs: Any) -> AtcHttp:
    from atc.client import AtcHttp

    return AtcHttp(kwargs["url"], Path(kwargs["cert"]).expanduser(), Path(kwargs["key"]).expanduser())


def main(argv: list[str] | None = None, *, client_factory: Callable[..., Any] = _default_client) -> int:
    p = argparse.ArgumentParser(description="Import BAU's projects.yaml into ATC project metadata")
    p.add_argument("yaml_path", type=Path)
    p.add_argument("--dry-run", action="store_true", help="show what would be sent; make no calls")
    p.add_argument("--atc-url", default=DEFAULT_URL)
    p.add_argument("--cert", type=Path, default=DEFAULT_CERT)
    p.add_argument("--key", type=Path, default=DEFAULT_KEY)
    args = p.parse_args(argv)

    projects = parse_projects_yaml(args.yaml_path)
    if args.dry_run:
        for ident, entry in projects.items():
            print(f"would PUT /api/projects/{ident} {project_body(entry)}")
        print(f"{len(projects)} projects (dry run, nothing sent)")
        return 0

    atc = client_factory(url=args.atc_url, cert=args.cert, key=args.key)
    r = import_projects(atc, projects)
    print(f"updated {len(r.updated)}: {', '.join(r.updated)}")
    if r.unknown:
        print(f"unknown to ATC ({len(r.unknown)}): {', '.join(r.unknown)}")
    return 1 if r.unknown else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
