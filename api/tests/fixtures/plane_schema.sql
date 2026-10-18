-- The slice of Plane's schema that ATC reads, as verified against Plane v1.4.2 and
-- the live database on Luke (18 Oct 2026). See "Plane schema ATC reads" in the plan.
-- Types follow Plane: uuid ids, timestamptz for *_at (except issues.archived_at, a date),
-- double precision sort_order. Created as the container's superuser, who stands in for
-- the role `plane`. There are deliberately no foreign keys: ATC must not depend on them.

CREATE TABLE public.workspaces (
    id uuid PRIMARY KEY,
    slug varchar(48) NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE TABLE public.projects (
    id uuid PRIMARY KEY,
    workspace_id uuid NOT NULL,
    identifier varchar(12) NOT NULL,
    name varchar(255) NOT NULL,
    archived_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE TABLE public.states (
    id uuid PRIMARY KEY,
    project_id uuid NOT NULL,
    name varchar(255) NOT NULL,
    "group" varchar(20) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE TABLE public.modules (
    id uuid PRIMARY KEY,
    project_id uuid NOT NULL,
    name varchar(255) NOT NULL,
    status varchar(20) NOT NULL,
    sort_order double precision NOT NULL DEFAULT 65535,
    archived_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE TABLE public.issues (
    id uuid PRIMARY KEY,
    project_id uuid NOT NULL,
    sequence_id integer NOT NULL,
    name varchar(255) NOT NULL,
    state_id uuid,
    priority varchar(30) NOT NULL DEFAULT 'none',
    sort_order double precision NOT NULL DEFAULT 65535,
    parent_id uuid,
    description_stripped text,
    archived_at date,
    is_draft boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE TABLE public.module_issues (
    id uuid PRIMARY KEY,
    module_id uuid NOT NULL,
    issue_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

-- Granted to atc per the spec's access list; ATC does not read these yet.
CREATE TABLE public.labels (
    id uuid PRIMARY KEY,
    project_id uuid,
    name varchar(255) NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);

CREATE TABLE public.issue_labels (
    id uuid PRIMARY KEY,
    issue_id uuid NOT NULL,
    label_id uuid NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    deleted_at timestamptz
);
