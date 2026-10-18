<img src="docs/logo.png" alt="atc logo" width="200" align="right"/>

# atc: Air Traffic Control for Plane

Arrange Plane projects and modules into Backlog, Up next and In progress, sized in story points. ATC is informational for Martin and authoritative for Claude sessions ("what's next?") and for BAU, the overnight worker.

## Support

If you find this useful, please consider buying me a coffee:

[![Donate with PayPal](https://www.paypalobjects.com/en_GB/i/btn/btn_donate_SM.gif)](https://www.paypal.com/donate?hosted_button_id=Q3BESC73EWVNN&custom=atc)

## Table of Contents

<!-- toc -->

- [What it is](#what-it-is)
- [API](#api)
  * [Reconcile and health](#reconcile-and-health)
- [Points pass](#points-pass)
- [Container image](#container-image)
- [Architecture Diagram](#architecture-diagram)
- [Repository Layout](#repository-layout)
- [Architecture Diagrams](#architecture-diagrams)
- [Support](#support)

<!-- tocstop -->

## What it is

A board at `atc.plane.home.nakomis.com`: three manually ordered columns of project and module cards, every open work item sized in story points (1 point is about one day of Martin's own work), with column and card totals. The Plane MCP and BAU read it through an HTTP API. Project metadata Plane cannot store (repo, deploys, deploy action, BAU enabled) lives here too.

The full design is in [docs/superpowers/specs/2026-10-18-atc-design.md](docs/superpowers/specs/2026-10-18-atc-design.md).

## API

All JSON; ATC adds no auth of its own (Leia's mTLS is the gate).

| Method and path | Purpose |
|-----------------|---------|
| `GET /api/board[?all=true]` | Columns of cards, with points and totals |
| `POST /api/move` | Move a project or module card (`kind`, `id`, `to_column`, `before_id?`) |
| `POST /api/reorder` | Reorder a module within its project card |
| `GET /api/next` | The next item to work on, with up to two runners-up |
| `GET /api/priority` | Every open item ref, in priority order |
| `GET /api/projects[?bau_enabled=true]`, `GET`/`PUT /api/projects/{uuid\|IDENT}` | Project metadata (repo, deploys, deploy action, BAU enabled) |
| `GET`/`PUT /api/work-items/{uuid}/points` | Story points (`if_unestimated` never overwrites) |
| `GET /api/work-items?unestimated=true[&project=IDENT]` | Open items still without points |
| `GET /api/health` | `{ok, missing, last_reconcile, hidden}`; HTTP 503 when not ok |

### Reconcile and health

A reconcile pass runs at start-up and then every `ATC_RECONCILE_SECONDS` (default 300; `0` turns the loop off). It gives new Plane projects, their Unsorted groups and new modules a row at the bottom of Backlog, hides ATC rows whose Plane project or module is deleted or archived, and unhides them when they return. It never deletes rows, never moves an existing row, and takes the same advisory lock as moves. A failed pass is logged and makes `/api/health` report 503 until the next one succeeds.

`/api/health` is 503 when the database is unreachable, when the `atc` role cannot see a Plane column ATC reads (`missing` lists each as `table.column`; the reconcile writes nothing meanwhile), or when the last reconcile failed. `hidden` counts the ATC rows currently hidden.

## Points pass

`uv --directory api run atc-points-pass [--project IDENT]... [--dry-run] [--model M]` runs one `claude -p` session (Martin's Max login) per batch of 40 open, unestimated tickets in each project, and writes the answers through the API with source `claude-estimate` and `if_unestimated`, so a number already set is never overwritten (a 409 counts as skipped). Sessions run locked down (no tools, no saved session, neutral temp directory) on `--model` (default `claude-opus-5-5`); a usage limit stops the pass with a non-zero exit, as do two consecutive session failures. Ticket text goes into the prompt as nonce-delimited, untrusted data. `--atc-url`, `--cert` and `--key` default to `https://atc.plane.home.nakomis.com` and `~/.config/nakomis/client.{crt,key}`. Re-run it any time for new unestimated items; try `--dry-run` on one small project first.

## Container image

One image serves the API and the built board (`container/Dockerfile`: pnpm builds `web/dist`, uv installs `api`, the result runs as a non-root user on port 8000 with `ATC_STATIC_DIR=/app/static`). It is linux/amd64, for Mace.

```bash
docker build --platform linux/amd64 --provenance=false --sbom=false -f container/Dockerfile -t atc:local .
docker run --rm -e ATC_DATABASE_URL=postgresql://atc:...@host:5432/plane -p 8000:8000 atc:local
```

CI builds the image on every pull request (not pushed). On a push to `main` it publishes `registry.home.nakomis.com/nakomis/atc:<version>-<sha7>`, where `<version>` is `api/pyproject.toml`'s `version`; the patch is bumped while that tag already exists, because the repository is `ALLOW_ONCE`. The job fails with a clear error if a secret is missing. It needs four repository secrets (the same values home-infra uses; see `docs/runbooks/nexus.md` there, "Publishing from CI"):

| Secret | Content |
|--------|---------|
| `NEXUS_DOCKER_USER` | Nexus user allowed to push to `registry.home.nakomis.com` |
| `NEXUS_DOCKER_PASSWORD` | That user's password |
| `NEXUS_CLIENT_CERT` | Home mTLS client certificate (PEM) |
| `NEXUS_CLIENT_KEY` | Its private key (PEM) |

The container exits if the database is unreachable at start-up (the schema migration waits 30 seconds for a connection), so run it with a restart policy.

## Architecture Diagram

![Architecture](docs/architecture/atc.svg)

## Repository Layout

| Path | Purpose |
|------|---------|
| `api/` | FastAPI service (Python 3.12, uv) |
| `web/` | Board UI (React, Vite, Tailwind 4, Biome, Vitest, pnpm) |
| `container/` | Image build for the single ATC container |
| `docs/` | Architecture diagrams and the design spec |

(The code directories arrive with the first feature work; see the ATC project in Plane.)

## Architecture Diagrams

`docs/architecture/atc.drawio` is the source for the diagram. The SVG is auto-regenerated on commit by the pre-commit hook in `.githooks/pre-commit`.

To activate the hook after cloning:

```bash
git config core.hooksPath .githooks
```

## Support

If you find this useful, please consider buying me a coffee:

[![Donate with PayPal](https://www.paypalobjects.com/en_GB/i/btn/btn_donate_SM.gif)](https://www.paypal.com/donate?hosted_button_id=Q3BESC73EWVNN&custom=atc)
