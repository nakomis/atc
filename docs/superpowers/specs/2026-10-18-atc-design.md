# ATC: Air Traffic Control for Plane — design

Date: 18 October 2026
Status: approved by Martin 18 Oct 2026 (session "bau-pipeline").
Home once approved: a new repo `nakomis/atc` (created with `/start-claude-project`), `docs/superpowers/specs/2026-10-18-atc-design.md`.

## 1. Intent

Martin has 37 Plane projects and about 640 open work items. What he works on next is whatever pops into his head. ATC (`atc.plane.home.nakomis.com`) turns that into a decision already made: a board where he arranges whole projects and their modules into Backlog, Up next and In progress, in his own order, with every piece of work sized.

ATC is informational for Martin. It is authoritative for two machines:
- **Claude sessions.** Martin usually asks "what's next?" in a Claude session, so the most-used part of ATC is the Plane MCP answering that question from ATC.
- **BAU**, the overnight worker, which takes its priorities and its per-project settings from ATC.

ATC is also the home for project metadata Plane cannot store (Plane Community Edition has no custom fields), replacing BAU's `config/projects.yaml`.

## 2. Goals, non-goals, anti-goals

**Goals**
- A three-column board of projects and modules, manually ordered, that Martin can rearrange in seconds.
- Every work item sized in story points (1 point ≈ 1 day of Martin's own work), with column totals.
- "What's next?" answerable by any Claude session through the Plane MCP.
- BAU ordered by ATC and configured from ATC.
- ATC's data lives in Plane's Postgres and is backed up with Plane.

**Non-goals**
- Replacing Plane's own UI for tickets. ATC arranges projects and modules; tickets are edited in Plane.
- Enforcing anything on Martin. Nothing is blocked by ATC; it informs.
- Time tracking, burndown, velocity charts (points make them possible later; not now).
- Multi-user anything. One user, Martin, behind mTLS.

**Anti-goals**
- Touching Plane's own tables (writes) or its migrations. ATC only reads Plane's tables; it writes only its own schema. A Plane upgrade must never break on ATC's account, and ATC must survive a Plane upgrade or report clearly what changed.
- Another place Martin has to keep in sync by hand. New tickets get points and a module at creation time through the MCP.

## 3. Decisions record (Martin, 18 Oct 2026)

| Question | Decision |
|---|---|
| Columns | Backlog, Up next, In progress. (May change; keep the column set data-driven.) |
| What is on the board | Projects, and their modules. Modules are Plane's modules; the Taiga-style `epic` parent items were retired into modules on 18 Oct 2026. |
| Moving | A single module can move between columns. A whole project can move: it picks up its modules in the source and target columns, but not those in the third column. |
| Column contents | One ordered list of cards per column. A card is either a whole project or a single module. A project not moved as a whole shows its modules as separate single-module cards, labelled with the project (approved from the mock-up). |
| Sorting | Every column is manually sortable; new items go in at the bottom. Modules are sortable within their project card. |
| Loose tickets | Tickets in no module sit in an "Unsorted" group per project, which behaves like a module. |
| Story points | Required when creating a ticket through the MCP. 1 point ≈ 1 day of Martin's work. Any positive integer up to a maximum; no Fibonacci, no 8-point cap. |
| Existing tickets | Claude estimates points for every existing open ticket in one pass; Martin corrects as he goes. |
| Who it is for | Informational for Martin; BAU prioritises by it. |
| Where Martin asks "what's next?" | In a Claude session, so the MCP must answer from ATC. |
| Project metadata | Repo, deploys, deploy action move from BAU's `projects.yaml` into ATC. |
| Storage | New tables in the existing Plane Postgres, backed up the same way. |
| Hosting | Plane's data tier is on Luke, its app tier on Mace: ATC follows that split. |

## 4. Data

**Where:** a schema `atc` in the `plane` database on Luke's `plane-db`. `plane/deployment/backup.sh` already `pg_dump`s the whole database with no schema filter, so ATC is backed up nightly with no change. Plane's migrations only manage Plane's own schema.

**Access:** a dedicated Postgres role `atc` with all privileges on schema `atc` and `SELECT` on the Plane tables it reads (projects, modules, module membership, work items, states, labels). It never writes Plane's tables. Its password is generated and stored in SSM (`/atc/postgres/password`) and rendered by Ansible, like Plane's.

**Tables (shape is the builder's; these are the facts each must hold):**
- `atc.project`: one row per Plane project id. Column (`backlog | next | in_progress`), position within that column when the project is a whole-project card, and project metadata: `repo` (e.g. `nakomis/nakom.is`, nullable for catch-all projects), `deploys` (bool), `deploy_action` (text), `bau_enabled` (bool, replaces "is it in projects.yaml").
- `atc.module`: one row per Plane module id, plus one synthetic "Unsorted" row per project. Column, position within the column (when shown as a single-module card), position within its project card.
- `atc.work_item`: one row per Plane work item id (1-1 metadata, Martin's suggestion). `points` (integer, 1..`max_points`), `points_source` (`claude-estimate | martin | mcp`), timestamps. Room for more columns later; JSON only if a field is genuinely free-form.
- Rows are created lazily: a Plane project/module/work item with no ATC row is treated as Backlog, bottom, unestimated, and gets a row on first touch or on the next reconcile.

**Ordering:** each list (a column's cards; a project card's modules) uses a sortable key so a drag writes one row (fractional/lexicographic ranks, builder's choice). New items get a rank after the current last.

**Ticket order within a module:** Plane's own `sort_order` on work items (what Martin gets by dragging in Plane's board view). ATC does not store a separate ticket order.

**Deletions and drift:** a reconcile pass (on API start and every few minutes) notes Plane rows that vanished (deleted/archived projects and modules) and hides their ATC rows without deleting them.

## 5. Board behaviour

- A column renders its ordered cards. A **project card** appears in a column when the project itself is in that column; it lists, in order, that project's modules **that are in the same column**, plus its Unsorted group if Unsorted is in that column. A project's modules in other columns appear in those columns as **single-module cards** labelled `PROJ · Module name`.
- **Move a module** (drag to another column): it becomes a single-module card at the bottom of the target column, or joins its project card there if the project is in that column.
- **Move a project** from column A to column B: the project and every one of its modules currently in A or B end up in B (in their existing relative order, modules in B keeping their place first, then those from A); modules in the third column stay put.
- **Reorder** cards in a column; reorder modules within a project card.
- **Points:** each card shows the remaining points (sum over open work items); each column header shows its total. Unestimated items are counted and shown ("+12 unestimated").
- **Ticket drill-down:** a module or Unsorted group expands to list its open tickets in Plane `sort_order` with points, each linking to Plane. Points are editable inline (writes `points_source = martin`).
- **Project settings:** each project has a small settings panel for repo, deploys, deploy action and `bau_enabled`.
- Closed modules (status completed/cancelled) and projects with no open work collapse out of the board by default.

## 6. API (ATC service)

A small HTTP API on the ATC backend, the only thing that touches the `atc` schema. Behind Leia's mTLS like everything else; the MCP and BAU use it, not Postgres.

- `GET /api/board` — the three columns, cards in order, nested modules, points.
- `POST /api/move` — `{kind: project|module, id, to_column, before_id?}` (moves and reorders in one call).
- `POST /api/reorder` — reorder modules within a project card.
- `GET /api/next` — the next ticket: the first open ticket (Plane `sort_order`) of the first module/Unsorted group in In progress, in board order; if In progress has none, Up next. Returns ticket ref, title, module, project, points, plus the two runners-up.
- `GET/PUT /api/work-items/{id}/points`; `GET/PUT /api/projects/{id}` (metadata).
- `GET /api/projects?bau_enabled=true` — BAU's project list (identifier, repo, deploys, deploy_action) in board priority order.
- `GET /api/priority` — every open work item ref in priority order (column, then card order, then module order within project, then Plane sort_order), for BAU.

## 7. Plane MCP changes (`mcps/plane-mcp`)

- `create_work_item` requires `points` (integer 1..`max_points`) and accepts `module`; it creates the item in Plane and then sets its points through ATC's API. Without `points` it refuses with a clear message. (Martin: no Fibonacci, no 8 cap.)
- `update_work_item` accepts `points`.
- New tools: `atc_board` (summary of the three columns), `whats_next` (wraps `GET /api/next`), `set_project_meta`.
- The MCP's description of `create_work_item` explains the point scale: 1 point ≈ 1 day of Martin's own work.
- Skills: `/start-plane` with no ref calls `whats_next` and proposes the top item. `/start-claude-project` Step 3a sets project metadata through `set_project_meta` instead of a BAU PR. Martin's global CLAUDE.md gains a line: "what's next?" means ask ATC first.

## 8. BAU changes

- **Project list and settings** come from `GET /api/projects?bau_enabled=true`, replacing `config/projects.yaml` (removed after migration).
- **Priority:** the sweep, triage and pickup process items in `GET /api/priority` order instead of creation date / Plane priority.
- **Failure mode:** if ATC is unreachable at preflight, BAU falls back to its last cached copy of the project list and priority (kept on Cere, refreshed every successful run) and records `stop_reason`/snapshot `atc: stale`; with no cache it stops with `preflight: atc`.
- This lands in BAU as its own work item after ATC's API exists.

## 9. The points pass

A one-off Claude pass estimates every open work item that has no points: one session per project, given each ticket's title, description, module and a short calibration note ("1 point ≈ one day of Martin's own focused work; a typical small bug fix is 1, a feature with infra and tests is 3–8, anything over 20 should probably be split"). Writes via the API with `points_source = claude-estimate`. Martin corrects in ATC or Plane over time; corrections become `martin`. Same pass can be re-run for new unestimated items.

## 10. Hosting and delivery

- **App tier on Mace**, beside Plane's app tier: one container for the API (Python/FastAPI) serving the built web app (React/Vite/Tailwind/Biome/Vitest, as BAU's dashboard). Image built by CI, pushed to `docker.home.nakomis.com`, pulled by Mace's playbook — the house pattern of installing CI-built artefacts, not building on the host.
- **Data on Luke:** the `atc` schema and role created by Luke's playbook (idempotent), reached over Luke's LAN Postgres port as Plane's app tier does.
- **Leia** gets `atc.plane.home.nakomis.com` with the usual mTLS vhost, proxying to the ATC container on Mace.
- Plane project `ATC` and repo `nakomis/atc` via `/start-claude-project` (which also enrols it in BAU).

## 11. Claude's calls (Martin to check)

- `max_points` = 100 (configurable).
- A separate `atc` schema and role rather than tables among Plane's, so Plane migrations and ATC never collide and ATC never holds Plane's superuser password.
- ATC owns its tables behind an API; the MCP and BAU never connect to Postgres.
- Ticket order within a module reuses Plane's `sort_order` rather than a second ordering.
- Points stored in ATC, not Plane's hidden legacy `point` field (not shown in Plane's UI and liable to change in an upgrade) nor Plane estimates (a short fixed list per project, not exposed in the public API).
- BAU keeps a cached copy so an ATC outage never stops the night outright.
- **Open** means a work item whose Plane state group is not `completed` or `cancelled` (so triage, backlog, unstarted and started all count). Totals, `/api/next`, `/api/priority` and the points pass use this.
- **An item in several modules** (Plane allows it) belongs, for ATC, to the first of its modules in board order; totals and priority count it once.
- **Unsorted** holds open items in no open module (no module, or only completed/cancelled ones). For existing projects it starts in the project's column; new projects and their Unsorted group start at the bottom of Backlog.
- **A project card** always shows in its project's column, even when empty (greyed "nothing here"), so a whole-project move always has something to grab; single-module cards elsewhere are unaffected.
- **BAU and Backlog:** the column is an ordering key only. BAU still works Backlog items when there is allowance, after In progress and Up next (Martin: informational for him, priority for BAU). Within a module, Plane `sort_order` decides; ties fall back to the old priority-then-created order. Sweep, triage and pickup all use the same order.
- **Auth:** the MCP and BAU reach ATC through Leia with the same mTLS client certificates they already use for Plane; ATC adds no auth of its own.
- **`create_work_item`:** creates in Plane, then sets points via ATC. If ATC fails, the ticket is kept and the MCP returns an error naming the ticket and saying its points weren't set; the reconcile shows it as unestimated. Tickets created outside the MCP (Plane UI) appear unestimated until the points pass is re-run, which is a manual command in the ATC repo.
- **Migration from `projects.yaml`:** a one-off import seeds `atc.project`; the per-ticket `repo:` override stays in BAU (it is ticket data, not project data); the YAML is deleted after BAU's first successful night on ATC.
- **Grants:** the Luke playbook creates the `atc` role and schema and uses `ALTER DEFAULT PRIVILEGES` so tables added by later Plane migrations stay readable; the reconcile reports any Plane table it can no longer read.
- **Delivery:** `/start-claude-project` provides the CI image build; one production environment; the Mace compose for ATC lives in home-infra beside Plane's app compose.
- **Keys:** the API uses Plane UUIDs internally and returns project identifiers alongside them, so renames (NAKO → NAKIS) don't break BAU.
- **The points pass** is a script in the ATC repo that runs Claude sessions per project on the Max subscription; Claude runs it once at go-live.

## 12. Left to the builder

- Exact table shapes and rank encoding.
- Reconcile cadence and how vanished Plane rows are shown.
- UI details beyond the approved mock-up (`.superpowers/brainstorm/.../atc-board.html` in the bau repo): drag library, styling, empty states.
- How the MCP authenticates to ATC (mTLS client cert it already has for Plane).
