#!/usr/bin/env bash
# Idempotent generator for the langflow-db-secret Secret.
# Must be run BEFORE applying langflow-postgres.yaml. Safe to re-run --
# does not overwrite an existing secret, so Postgres data isn't orphaned by
# a password change after the DB has already been initialized with the
# original password. Mirrors gateway/openshift/create-keycloak-db-secret.sh.
set -euo pipefail

NAMESPACE="${1:-otel25-sdg}"

if oc get secret langflow-db-secret -n "${NAMESPACE}" >/dev/null 2>&1; then
  echo "langflow-db-secret already exists in ${NAMESPACE} -- leaving it as-is."
  exit 0
fi

DB_PASSWORD=$(openssl rand -base64 24)

oc create secret generic langflow-db-secret \
  -n "${NAMESPACE}" \
  --from-literal=username=langflow \
  --from-literal=password="${DB_PASSWORD}"

echo "Created langflow-db-secret in ${NAMESPACE} with a generated password."
