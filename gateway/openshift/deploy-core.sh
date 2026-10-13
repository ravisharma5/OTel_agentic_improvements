#!/usr/bin/env bash
# deploy-core.sh -- Apply the cluster-hostname-dependent manifests (Keycloak,
# Gateway, AuthPolicy) with the current cluster's actual apps domain substituted
# in, instead of a hardcoded one.
#
# 2026-10-13: added after discovering mid-migration (sandbox1330 -> sandbox3435)
# that keycloak.yaml, gateway.yaml, and auth-policy.yaml all had sandbox1330's
# hostname hardcoded, and the live fix for sandbox3435 was never committed --
# the next migration would have hit the exact same manual find/replace again.
#
# Prerequisites (not handled by this script -- see the numbered manifests in
# this directory and apply them first): namespace.yaml, the OSSM/cert-manager/
# RHCL/Authorino/Keycloak operator subscriptions, istio.yaml/istio-cni.yaml,
# kuadrant.yaml, and create-keycloak-db-secret.sh.
#
# Usage: bash deploy-core.sh
#   GATEWAY_APPS_DOMAIN can be set explicitly in the environment to override
#   auto-detection, e.g. for a dry run against a manifest diff before the new
#   cluster exists.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "${GATEWAY_APPS_DOMAIN:-}" ]; then
  echo "Detecting cluster apps domain..."
  GATEWAY_APPS_DOMAIN=$(oc get ingresses.config.openshift.io cluster -o jsonpath='{.spec.domain}')
  if [ -z "$GATEWAY_APPS_DOMAIN" ]; then
    echo "ERROR: could not auto-detect apps domain. Set GATEWAY_APPS_DOMAIN explicitly." >&2
    exit 1
  fi
fi
export GATEWAY_APPS_DOMAIN
echo "Using GATEWAY_APPS_DOMAIN=${GATEWAY_APPS_DOMAIN}"
echo ""

echo "[1/3] Applying keycloak.yaml (Postgres + PVC + Keycloak CR, 2 instances)..."
envsubst '${GATEWAY_APPS_DOMAIN}' < "${SCRIPT_DIR}/keycloak.yaml" | oc apply -f -

echo ""
echo "Waiting for Keycloak to report Ready before configuring realm/clients..."
oc wait keycloak/mcp-keycloak -n otel25-gateway --for=condition=Ready --timeout=300s

echo ""
echo "[2/3] Running configure-keycloak.sh to create realm/clients/secrets..."
bash "${SCRIPT_DIR}/configure-keycloak.sh" otel25-gateway mcp-keycloak

echo ""
echo "[3/3] Applying gateway.yaml and auth-policy.yaml..."
envsubst '${GATEWAY_APPS_DOMAIN}' < "${SCRIPT_DIR}/gateway.yaml" | oc apply -f -
envsubst '${GATEWAY_APPS_DOMAIN}' < "${SCRIPT_DIR}/auth-policy.yaml" | oc apply -f -

echo ""
echo "=== Done ==="
echo "Next: deploy domain MCP servers (mcp/openshift/), Prism mocks (backends/openshift/),"
echo "then the httproute-*.yaml / mcpsr-*.yaml / mcpvs-*.yaml registrations in this directory."
echo ""
echo "Known gap carried forward (not fixed): UDR/NWDAF gateway-mediated calls return 4xx"
echo "despite direct backend reachability working -- root cause not yet found. See"
echo ".planning/phases/04-sdg-pipeline-and-dataset-production/04-LEARNINGS.md."
