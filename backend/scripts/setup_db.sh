#!/usr/bin/env bash
#
# SafeR CI — local PostgreSQL + PostGIS setup (no Docker required)
#
# Creates the application role, database, and PostGIS extension against a
# *running* local PostgreSQL server. Idempotent — safe to re-run.
#
# Prerequisites (install once, no containers):
#   Debian/Ubuntu: sudo apt install postgresql postgresql-<ver>-postgis-3
#   macOS (brew):  brew install postgresql postgis && brew services start postgresql
#
# Usage:
#   ./scripts/setup_db.sh
#
# Override any of these via environment:
#   DB_NAME (safer_ci)  DB_USER (safer)  DB_PASSWORD (safer_pass)
#   DB_HOST (localhost)  DB_PORT (5432)
#
set -euo pipefail

DB_NAME="${DB_NAME:-safer_ci}"
DB_USER="${DB_USER:-safer}"
DB_PASSWORD="${DB_PASSWORD:-safer_pass}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

# Choose how to run psql as a superuser. On Debian/Ubuntu the postgres role is
# reachable via `sudo -u postgres`; on macOS/brew the current user is a superuser.
if command -v sudo >/dev/null 2>&1 && id postgres >/dev/null 2>&1; then
  super() { sudo -u postgres psql -v ON_ERROR_STOP=1 -p "$DB_PORT" "$@"; }
else
  super() { psql -v ON_ERROR_STOP=1 -h "$DB_HOST" -p "$DB_PORT" -d postgres "$@"; }
fi

echo "==> Ensuring role '$DB_USER' exists"
if [ -z "$(super -tAc "SELECT 1 FROM pg_roles WHERE rolname='${DB_USER}'")" ]; then
  super -c "CREATE ROLE ${DB_USER} LOGIN PASSWORD '${DB_PASSWORD}';"
  echo "    created role ${DB_USER}"
else
  echo "    role already exists"
fi

echo "==> Ensuring database '$DB_NAME' exists"
if [ -z "$(super -tAc "SELECT 1 FROM pg_database WHERE datname='${DB_NAME}'")" ]; then
  super -c "CREATE DATABASE ${DB_NAME} OWNER ${DB_USER};"
  echo "    created database ${DB_NAME}"
else
  echo "    database already exists"
fi

echo "==> Enabling PostGIS extension in '$DB_NAME'"
super -d "$DB_NAME" -c "CREATE EXTENSION IF NOT EXISTS postgis;"

echo
echo "Done. Put this in backend/.env:"
echo "DATABASE_URL=postgresql+asyncpg://${DB_USER}:${DB_PASSWORD}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
