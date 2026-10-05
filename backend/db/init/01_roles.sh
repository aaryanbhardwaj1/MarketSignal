#!/usr/bin/env bash
# Creates the MarketSignal role topology (ADR-0009). Runs once, as the bootstrap superuser:
#   - by the postgres image's /docker-entrypoint-initdb.d on first container start, or
#   - explicitly in CI after the service container is up.
#
#   ms_owner : owns the schema; used only by Alembic migrations.
#   ms_app   : runtime role for the API and worker. LOGIN, NOSUPERUSER, NOBYPASSRLS, owns nothing.
#              Being neither owner nor superuser means FORCE ROW LEVEL SECURITY applies to it.
#
# Passwords come from the environment; the defaults are clearly marked dev-only.
set -euo pipefail

: "${POSTGRES_USER:?POSTGRES_USER must be set}"
: "${POSTGRES_DB:?POSTGRES_DB must be set}"
MS_OWNER_PASSWORD="${MS_OWNER_PASSWORD:-dev-only-insecure-owner}"
MS_APP_PASSWORD="${MS_APP_PASSWORD:-dev-only-insecure-app}"

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v owner_pw="$MS_OWNER_PASSWORD" -v app_pw="$MS_APP_PASSWORD" -v db="$POSTGRES_DB" <<'EOSQL'
SELECT format('CREATE ROLE ms_owner LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEROLE PASSWORD %L', :'owner_pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ms_owner') \gexec
SELECT format('CREATE ROLE ms_app LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD %L', :'app_pw')
WHERE NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'ms_app') \gexec

SELECT format('ALTER DATABASE %I OWNER TO ms_owner', :'db') \gexec
SELECT format('GRANT CONNECT ON DATABASE %I TO ms_app', :'db') \gexec
ALTER SCHEMA public OWNER TO ms_owner;
GRANT USAGE ON SCHEMA public TO ms_app;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;

-- pgvector is not a trusted extension; create it here, as the bootstrap superuser.
CREATE EXTENSION IF NOT EXISTS vector;
EOSQL

echo "marketsignal roles initialised (ms_owner, ms_app)"
