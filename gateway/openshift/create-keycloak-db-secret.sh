#!/usr/bin/env bash
# Idempotent generator for the keycloak-db-secret Secret.
# Must be run BEFORE applying keycloak.yaml. Safe to re-run -- does not
# overwrite an existing secret, so Postgres data isn't orphaned by a
# password change after the DB has already been initialized with the
# original password.
set -euo pipefail

NAMESPACE="${1:-otel25-gateway}"

if oc get secret keycloak-db-secret -n "${NAMESPACE}" >/dev/null 2>&1; then
  echo "keycloak-db-secret already exists in ${NAMESPACE} -- leaving it as-is."
  exit 0
fi

DB_PASSWORD=$(openssl rand -base64 24)

oc create secret generic keycloak-db-secret \
  -n "${NAMESPACE}" \
  --from-literal=username=keycloak \
  --from-literal=password="${DB_PASSWORD}"

echo "Created keycloak-db-secret in ${NAMESPACE} with a generated password."
