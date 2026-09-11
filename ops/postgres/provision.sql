-- roles for one application database, run by the bootstrap superuser against that database.
-- idempotent: converges role attributes, passwords, memberships, grants and ownership, so it also takes over a volume whose tables the bootstrap superuser created
--
-- env: DB_MIGRATOR_ROLE DB_RUNTIME_ROLE DB_MIGRATOR_PASSWORD DB_RUNTIME_PASSWORD, plus the libpq PGHOST PGDATABASE PGUSER PGPASSWORD of the bootstrap superuser
\set ON_ERROR_STOP on
\getenv migrator DB_MIGRATOR_ROLE
\getenv runtime DB_RUNTIME_ROLE
\getenv migrator_password DB_MIGRATOR_PASSWORD
\getenv runtime_password DB_RUNTIME_PASSWORD

SELECT :{?migrator} AND :{?runtime} AND :{?migrator_password} AND :{?runtime_password} AS vars_set,
       (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) AS is_superuser
\gset
\if :vars_set
\else
DO $$ BEGIN RAISE EXCEPTION 'DB_MIGRATOR_ROLE, DB_RUNTIME_ROLE, DB_MIGRATOR_PASSWORD and DB_RUNTIME_PASSWORD must all be set'; END $$;
\endif
\if :is_superuser
\else
DO $$ BEGIN RAISE EXCEPTION 'run as the bootstrap superuser'; END $$;
\endif

-- a failed statement is logged with its text, and the statements below carry passwords
SET log_min_error_statement = panic;
SET log_statement = none;

SELECT :'migrator' ~ '^[a-z_][a-z0-9_]*$' AND :'runtime' ~ '^[a-z_][a-z0-9_]*$'
         AND :'migrator' <> :'runtime' AND current_user NOT IN (:'migrator', :'runtime') AS roles_ok,
       :'migrator_password' ~ '^[A-Za-z0-9_-]{16,}$' AND :'runtime_password' ~ '^[A-Za-z0-9_-]{16,}$'
         AND :'migrator_password' <> :'runtime_password'
         AND position('change-me' in :'migrator_password' || :'runtime_password') = 0 AS passwords_ok
\gset
\if :roles_ok
\else
DO $$ BEGIN RAISE EXCEPTION 'the migrator and runtime roles must be two distinct lowercase names, neither of them the bootstrap user'; END $$;
\endif
\if :passwords_ok
\else
DO $$ BEGIN RAISE EXCEPTION 'the two passwords must differ, be 16 or more characters of [A-Za-z0-9_-], they go into a connection url, and not be placeholders'; END $$;
\endif

SELECT format('CREATE ROLE %I', r) FROM unnest(ARRAY[:'migrator', :'runtime']) AS r
WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = r)
\gexec
ALTER ROLE :"migrator" WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'migrator_password';
ALTER ROLE :"runtime" WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS PASSWORD :'runtime_password';
-- membership in any other role hands over its rights, the migrator's ownership included
SELECT format('REVOKE %I FROM %I GRANTED BY %I', g.rolname, m.rolname, gr.rolname)
FROM pg_auth_members a
JOIN pg_roles g ON g.oid = a.roleid JOIN pg_roles m ON m.oid = a.member JOIN pg_roles gr ON gr.oid = a.grantor
WHERE m.rolname IN (:'migrator', :'runtime')
\gexec

SELECT current_database() AS dbname
\gset
REVOKE ALL ON DATABASE :"dbname" FROM PUBLIC, :"migrator", :"runtime";
GRANT CONNECT ON DATABASE :"dbname" TO :"migrator", :"runtime";
-- the maintenance and template databases admit every role by default
SELECT format('REVOKE CONNECT, TEMPORARY ON DATABASE %I FROM PUBLIC', datname)
FROM pg_database WHERE datname IN ('postgres', 'template1') AND datname <> current_database()
\gexec

REVOKE ALL ON SCHEMA public FROM PUBLIC, :"runtime";
GRANT USAGE ON SCHEMA public TO :"runtime";
GRANT USAGE, CREATE ON SCHEMA public TO :"migrator";

-- the migrator alters what migrations created, so it owns every relation; sequences owned by a column follow their table
SELECT format('ALTER %s %I.%I OWNER TO %I',
              CASE c.relkind WHEN 'v' THEN 'VIEW' WHEN 'm' THEN 'MATERIALIZED VIEW'
                             WHEN 'S' THEN 'SEQUENCE' WHEN 'f' THEN 'FOREIGN TABLE' ELSE 'TABLE' END,
              n.nspname, c.relname, :'migrator')
FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p', 'v', 'm', 'f', 'S')
  AND c.relowner <> :'migrator'::regrole
  AND NOT EXISTS (SELECT FROM pg_depend d
                  WHERE d.classid = 'pg_class'::regclass AND d.objid = c.oid AND d.deptype IN ('e', 'a', 'i'))
\gexec

GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO :"runtime";
REVOKE TRUNCATE, REFERENCES, TRIGGER ON ALL TABLES IN SCHEMA public FROM :"runtime";
GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO :"runtime";
ALTER DEFAULT PRIVILEGES FOR ROLE :"migrator" IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO :"runtime";
ALTER DEFAULT PRIVILEGES FOR ROLE :"migrator" IN SCHEMA public REVOKE TRUNCATE, REFERENCES, TRIGGER ON TABLES FROM :"runtime";
ALTER DEFAULT PRIVILEGES FOR ROLE :"migrator" IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO :"runtime";

\echo database roles converged for :dbname
