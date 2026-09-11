-- one-off replacement of the bootstrap superuser's password, run inside the database container over its local socket, so the old password is never needed
-- env: NEW_BOOTSTRAP_PASSWORD
\set ON_ERROR_STOP on
\getenv new_password NEW_BOOTSTRAP_PASSWORD

SELECT :{?new_password} AS given, (SELECT rolsuper FROM pg_roles WHERE rolname = current_user) AS is_superuser
\gset
\if :given
\else
DO $$ BEGIN RAISE EXCEPTION 'NEW_BOOTSTRAP_PASSWORD is not set'; END $$;
\endif
\if :is_superuser
\else
DO $$ BEGIN RAISE EXCEPTION 'connect as the bootstrap superuser'; END $$;
\endif

-- a failed statement is logged with its text, and the statements below carry the password
SET log_min_error_statement = panic;
SET log_statement = none;

SELECT length(:'new_password') >= 16 AND position('change-me' in :'new_password') = 0
         AND :'new_password' !~ '^(dev-|ops-dev)' AS strong
\gset
\if :strong
\else
DO $$ BEGIN RAISE EXCEPTION 'the new bootstrap password must have 16 or more characters and not be a placeholder or dev value'; END $$;
\endif

ALTER ROLE CURRENT_USER PASSWORD :'new_password';
\echo bootstrap password replaced for :USER
