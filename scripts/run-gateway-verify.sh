#!/usr/bin/env bash
# Wrapper script to run verify-gateway.sh with token from Keycloak
set -euo pipefail

MODE="${1:-all}"
GATEWAY_URL="https://mcp.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com/mcp"
KEYCLOAK_URL="https://mcp-keycloak-otel25-gateway.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com"
CLIENT_SECRET="***REDACTED-CLIENT-SECRET***"
USER_PASSWORD="***REDACTED-PASSWORD***"

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
