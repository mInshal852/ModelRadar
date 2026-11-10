#!/bin/sh
# Creates the least-privilege roles used by the application.
#   modelradar_worker : read/write (the only component that writes data)
#   modelradar_api    : read-only
# Tables are created later by the owner role (migrations); default privileges
# below make them accessible to the right roles automatically.
set -eu

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<EOSQL
CREATE ROLE modelradar_worker LOGIN PASSWORD '${WORKER_DB_PASSWORD}';
CREATE ROLE modelradar_api LOGIN PASSWORD '${API_DB_PASSWORD}';

REVOKE ALL ON DATABASE "${POSTGRES_DB}" FROM PUBLIC;
GRANT CONNECT ON DATABASE "${POSTGRES_DB}" TO modelradar_worker, modelradar_api;

REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO modelradar_worker, modelradar_api;

ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public
  GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO modelradar_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public
  GRANT USAGE, SELECT ON SEQUENCES TO modelradar_worker;
ALTER DEFAULT PRIVILEGES FOR ROLE ${POSTGRES_USER} IN SCHEMA public
  GRANT SELECT ON TABLES TO modelradar_api;
EOSQL
