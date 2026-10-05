#!/usr/bin/env bash
# Wrapper script to run verify-gateway.sh with token from Keycloak
set -euo pipefail

MODE="${1:-all}"
GATEWAY_HOST=$(oc get route mcp-gateway -n otel25-gateway -o jsonpath='{.spec.host}' 2>/dev/null)
GATEWAY_URL="https://${GATEWAY_HOST}/mcp"
KEYCLOAK_URL="https://$(oc get route -n otel25-gateway -l app=keycloak -o jsonpath='{.items[0].spec.host}')"
CLIENT_SECRET=$(oc get secret keycloak-client-secret-mcp-gateway -n otel25-gateway -o jsonpath='{.data.CLIENT_SECRET}' | base64 -d)
USER_PASSWORD=$(oc get secret keycloak-client-secret-mcp-gateway -n otel25-gateway -o jsonpath='{.data.USER_PASSWORD}' | base64 -d)

if [ -z "$GATEWAY_HOST" ] || [ -z "$CLIENT_SECRET" ] || [ -z "$USER_PASSWORD" ]; then
  echo "ERROR: Could not resolve gateway host or Keycloak credentials from the cluster (is oc authenticated against the right cluster/namespace?)"
  exit 1
fi

# Get fresh token
TOKEN=$(curl -sk -X POST "${KEYCLOAK_URL}/realms/mcp/protocol/openid-connect/token" \
  -d "grant_type=password&client_id=mcp-gateway&client_secret=${CLIENT_SECRET}&username=mcp-agent&password=${USER_PASSWORD}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")

if [ -z "$TOKEN" ] || [ "$TOKEN" = "null" ]; then
  echo "ERROR: Failed to get JWT token"
  exit 1
fi

echo "Token obtained (${#TOKEN} chars)"

if [ "$MODE" = "all" ]; then
  for m in initialize tools-list virtual-tmf tool-call; do
    echo ""
    echo "============================================"
    echo "Running mode: $m"
    echo "============================================"
    scripts/verify-gateway.sh "$m" "$GATEWAY_URL" "$TOKEN" || true
  done
else
  scripts/verify-gateway.sh "$MODE" "$GATEWAY_URL" "$TOKEN"
fi
