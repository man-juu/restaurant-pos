#!/bin/sh
# Runs once, when the dev database volume is first created (docker-entrypoint-initdb.d).
# Creates the login roles the API and read-only tools use. Migrations grant table privileges.
# Production creates these roles by the server runbook (slice 0.8), with real secrets.
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE pos_app LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '${APP_DB_PASSWORD}';
CREATE ROLE pos_readonly LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '${READONLY_DB_PASSWORD}';
CREATE ROLE pos_admin LOGIN NOSUPERUSER NOBYPASSRLS PASSWORD '${ADMIN_DB_PASSWORD}';
-- Backups only: reads every table (also future ones) through pg_read_all_data and must see
-- every tenant (BYPASSRLS), but cannot write anything. Restores use the owner role.
CREATE ROLE pos_backup LOGIN NOSUPERUSER BYPASSRLS PASSWORD '${BACKUP_DB_PASSWORD}';
GRANT pg_read_all_data TO pos_backup;
SQL
