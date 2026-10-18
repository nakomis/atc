"""Import of BAU's config/projects.yaml into ATC's project metadata.

Run at go-live: `atc-import-projects ~/repos/nakomis/bau/config/projects.yaml`. Every identifier must
land in `updated` (or `unchanged`); anything in `unknown` has no Plane project and needs looking at.

After seeding, ATC is the record. A re-run therefore fills only what is missing: a project whose
metadata is still all defaults gets the file's values in full; on any other project only an empty
`repo` or `deploy_action` is filled, and `deploys` and `bau_enabled` are left alone (False may be
Martin's choice). `--overwrite` sends every field from the file, replacing edits made in ATC.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml

from atc.client import DEFAULT_CERT, DEFAULT_KEY, DEFAULT_URL

if TYPE_CHECKING:  # pragma: no cover
    from atc.client import AtcHttp

DEFAULT_META = {"repo": None, "deploys": False, "deploy_action": "", "bau_enabled": False}


@dataclass
class ImportResult:
    updated: list[str] = field(default_factory=list)
    unchanged: list[str] = field(default_factory=list)  # nothing missing in ATC (re-runs)
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


def fill_missing(current: dict[str, Any], wanted: dict[str, Any]) -> dict[str, Any]:
    """The part of `wanted` that fills gaps in ATC's `current` metadata, never replacing an edit."""
    if all(current.get(k) == v for k, v in DEFAULT_META.items()):
        return wanted  # never set up in ATC: seed it in full
    return {k: wanted[k] for k in ("repo", "deploy_action") if not current.get(k) and wanted[k]}


def import_projects(atc: AtcHttp, projects: dict[str, dict], *, overwrite: bool = False) -> ImportResult:
    """Send each project's metadata; a 404 means ATC (Plane) has no such identifier.

    Without `overwrite`, ATC's current metadata is read first and only missing fields are sent.
    """
    result = ImportResult()
    for ident, entry in projects.items():
        body = project_body(entry)
        if not overwrite:
            status, current = atc.get_status(f"/api/projects/{ident}")
            if status == 404:
                result.unknown.append(ident)
                continue
            if not 200 <= status < 300:
                raise RuntimeError(f"GET /api/projects/{ident} returned {status}")
            body = fill_missing(current, body)
            if not body:
                result.unchanged.append(ident)
                continue
        status, _ = atc.put(f"/api/projects/{ident}", body)
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
    p.add_argument("--dry-run", action="store_true", help="show the file's values; make no calls")
    p.add_argument(
        "--overwrite", action="store_true", help="send every field from the file, replacing edits made in ATC"
    )
    p.add_argument("--atc-url", default=DEFAULT_URL)
    p.add_argument("--cert", type=Path, default=DEFAULT_CERT)
    p.add_argument("--key", type=Path, default=DEFAULT_KEY)
    args = p.parse_args(argv)

    projects = parse_projects_yaml(args.yaml_path)
    if args.dry_run:
        for ident, entry in projects.items():
            print(f"would PUT /api/projects/{ident} {project_body(entry)}")
        mode = "every field" if args.overwrite else "only fields missing in ATC"
        print(f"{len(projects)} projects (dry run, nothing sent; a real run sends {mode})")
        return 0

    atc = client_factory(url=args.atc_url, cert=args.cert, key=args.key)
    r = import_projects(atc, projects, overwrite=args.overwrite)
    print(f"updated {len(r.updated)}: {', '.join(r.updated)}")
    if r.unchanged:
        print(f"already set in ATC, left alone ({len(r.unchanged)}): {', '.join(r.unchanged)}")
    if r.unknown:
        print(f"unknown to ATC ({len(r.unknown)}): {', '.join(r.unknown)}")
    return 1 if r.unknown else 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
