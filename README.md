<img src="docs/logo.png" alt="atc logo" width="200" align="right"/>

# atc: Air Traffic Control for Plane

Arrange Plane projects and modules into Backlog, Up next and In progress, sized in story points. ATC is informational for Martin and authoritative for Claude sessions ("what's next?") and for BAU, the overnight worker.

## Support

If you find this useful, please consider buying me a coffee:

[![Donate with PayPal](https://www.paypalobjects.com/en_GB/i/btn/btn_donate_SM.gif)](https://www.paypal.com/donate?hosted_button_id=Q3BESC73EWVNN&custom=atc)

## Table of Contents

<!-- toc -->

- [What it is](#what-it-is)
- [Architecture Diagram](#architecture-diagram)
- [Repository Layout](#repository-layout)
- [Architecture Diagrams](#architecture-diagrams)
- [Support](#support)

<!-- tocstop -->

## What it is

A board at `atc.plane.home.nakomis.com`: three manually ordered columns of project and module cards, every open work item sized in story points (1 point is about one day of Martin's own work), with column and card totals. The Plane MCP and BAU read it through an HTTP API. Project metadata Plane cannot store (repo, deploys, deploy action, BAU enabled) lives here too.

The full design is in [docs/superpowers/specs/2026-10-18-atc-design.md](docs/superpowers/specs/2026-10-18-atc-design.md).

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
