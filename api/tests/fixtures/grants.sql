-- Test copy of the atc role, schema and grants.
--
-- Source of truth: home-infra `plane/deployment/atc-role.sql` (ATC-1). This file is that
-- script plus a fixed test password (production takes the password from SSM
-- `/atc/postgres/password` and sets it separately). Keep the two in step.
-- Run as the superuser standing in for `plane`, after plane_schema.sql.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'atc') THEN
        CREATE ROLE atc LOGIN;
    END IF;
END
$$;

-- Test only: production supplies this from SSM.
ALTER ROLE atc WITH LOGIN PASSWORD '0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef';

CREATE SCHEMA IF NOT EXISTS atc AUTHORIZATION atc;

GRANT USAGE ON SCHEMA public TO atc;

DO $$
DECLARE
    t text;
BEGIN
    FOREACH t IN ARRAY ARRAY[
        'workspaces', 'projects', 'modules', 'module_issues',
        'issues', 'states', 'labels', 'issue_labels'
    ] LOOP
        IF to_regclass('public.' || t) IS NOT NULL THEN
            EXECUTE format('GRANT SELECT ON public.%I TO atc', t);
        ELSE
            RAISE WARNING 'public.% does not exist yet; atc cannot read it', t;
        END IF;
    END LOOP;
END
$$;

ALTER DEFAULT PRIVILEGES FOR ROLE plane IN SCHEMA public GRANT SELECT ON TABLES TO atc;

ALTER ROLE atc SET search_path = atc, public;
