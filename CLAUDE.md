# atc

Air Traffic Control for Plane: a board that arranges Plane projects and modules into Backlog, Up next and In progress, sized in story points. Spec: `docs/superpowers/specs/2026-10-18-atc-design.md`. Read it before changing behaviour. Plane project: `ATC`.

## Stack

- **API:** Python 3.12, FastAPI, managed with `uv` (`uv sync`, `uv run pytest`, `uv run ruff check .`).
- **Web:** React, Vite, Tailwind 4, Biome, Vitest, pnpm (pinned via `packageManager`; never npm lockfiles, see Martin's start-claude-project notes on the Nexus proxy).
- **Data:** Postgres schema `atc` in Plane's own `plane` database on Luke (`plane-db`), backed up with Plane by its nightly `pg_dump`.
- **Delivery:** one container (API serving the built web app) built by CI and pushed to `docker.home.nakomis.com`; deployed to Mace by home-infra Ansible. Leia proxies `atc.plane.home.nakomis.com` with mTLS.
- Coverage minimum 70%. British English. No attribution lines in commits.

## Key decisions

- ATC only **reads** Plane's tables and **writes** only its own `atc` schema, through a dedicated role `atc` (password in SSM `/atc/postgres/password`). It never runs Plane migrations.
- The API is the only thing that touches `atc`. The Plane MCP and BAU are API clients over Leia's mTLS; ATC adds no auth of its own.
- Columns are data-driven: Backlog, Up next, In progress. A card is a whole project or a single module; projects and modules are manually ordered with sortable ranks (a drag writes one row).
- Moving a project takes its modules in the source and target columns with it, not those in the third column.
- Loose tickets sit in a synthetic "Unsorted" group per project. Ticket order within a module is Plane's `sort_order`.
- Story points live in `atc.work_item` (1..`max_points`, default 100; 1 point is about 1 day of Martin's work), not in Plane's legacy `point` field. `points_source` is `claude-estimate | martin | mcp`.
- "Open" means Plane state group not `completed` or `cancelled`. An item in several modules belongs to the first in board order.
- Rows are created lazily; a reconcile pass hides rows for deleted or archived Plane projects and modules.
- The API uses Plane UUIDs internally and returns project identifiers alongside them.
- BAU keeps a cached copy of the project list and priority, so an ATC outage never stops the night. Backlog is an ordering key only: BAU still works it after In progress and Up next.
- ATC replaces BAU's `config/projects.yaml`. Do not open projects.yaml PRs for new projects.

## Repository layout

| Path | Purpose |
|------|---------|
| `api/` | FastAPI service |
| `web/` | Board UI |
| `container/` | Image build |
| `docs/` | Diagrams and spec |

## Workflow

Always work on a feature branch and open a PR; branch and PR title carry the Plane ref, e.g. `atc-2-api` and `feat: board API (ATC-2)`.

## Architecture diagrams

Source: `docs/architecture/atc.drawio`; SVG auto-regenerated on commit by `.githooks/pre-commit`.

To activate the hook after cloning:
```bash
git config core.hooksPath .githooks
```
