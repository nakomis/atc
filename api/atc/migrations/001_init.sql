-- ATC's own schema. No foreign keys into Plane's tables: Plane's migrations must never
-- trip on ATC. Rank columns use COLLATE "C" so Postgres compares them byte-wise.

CREATE TABLE atc.schema_version (
    version int PRIMARY KEY,
    applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE atc.column_def (
    key text PRIMARY KEY,
    label text NOT NULL,
    position int NOT NULL,
    priority int NOT NULL
);

INSERT INTO atc.column_def (key, label, position, priority) VALUES
    ('backlog', 'Backlog', 0, 2),
    ('next', 'Up next', 1, 1),
    ('in_progress', 'In progress', 2, 0);

CREATE TABLE atc.project (
    plane_id uuid PRIMARY KEY,
    column_key text NOT NULL REFERENCES atc.column_def,
    rank text COLLATE "C" NOT NULL,
    repo text,
    deploys bool NOT NULL DEFAULT false,
    deploy_action text NOT NULL DEFAULT '',
    bau_enabled bool NOT NULL DEFAULT false,
    hidden_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE atc.module (
    id uuid PRIMARY KEY,
    project_id uuid NOT NULL,
    unsorted bool NOT NULL DEFAULT false,
    column_key text NOT NULL REFERENCES atc.column_def,
    column_rank text COLLATE "C" NOT NULL,
    card_rank text COLLATE "C" NOT NULL,
    hidden_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX module_one_unsorted_per_project ON atc.module (project_id) WHERE unsorted;

-- The upper bound on points is max_points, checked in the API so it stays configurable.
CREATE TABLE atc.work_item (
    plane_id uuid PRIMARY KEY,
    points int NOT NULL CHECK (points >= 1),
    points_source text NOT NULL CHECK (points_source IN ('claude-estimate', 'martin', 'mcp')),
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
