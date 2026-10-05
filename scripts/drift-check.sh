#!/usr/bin/env bash
# Drift-check: compare virtual server tool lists (YAML) against live gateway response.
# Exits 1 if any drift is detected.
set -euo pipefail

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

# Initialize session
INIT_RESPONSE=$(curl -sk -D /tmp/drift-headers \
  -X POST "${GATEWAY_URL}" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"drift-check","version":"1.0"}},"id":0}' \
  --max-time 30 2>/dev/null || echo "")

SESSION_ID=$(grep -i 'mcp-session-id' /tmp/drift-headers 2>/dev/null | tr -d '\r' | awk '{print $2}' || echo "")

if [ -z "$SESSION_ID" ]; then
  echo "ERROR: Could not get MCP session ID"
  exit 1
fi

# Send initialized notification
curl -sk -X POST "${GATEWAY_URL}" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: ${SESSION_ID}" \
  -H "Authorization: Bearer ${TOKEN}" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  --max-time 10 >/dev/null 2>&1 || true

DRIFT_FOUND=0

for pair in "tmf-tools:gateway/openshift/mcpvs-tmf.yaml" "nwdaf-tools:gateway/openshift/mcpvs-nwdaf.yaml" "camara-tools:gateway/openshift/mcpvs-camara.yaml" "infra-tools:gateway/openshift/mcpvs-infra.yaml"; do
  VS_NAME="${pair%%:*}"
  VS_FILE="${pair##*:}"

  echo "--- Checking ${VS_NAME} ---"

  # Get live tools from gateway
  LIVE_RESPONSE=$(curl -sk -X POST "${GATEWAY_URL}" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "Mcp-Session-Id: ${SESSION_ID}" \
    -H "Authorization: Bearer ${TOKEN}" \
    -H "X-Mcp-Virtualserver: otel25-gateway/${VS_NAME}" \
    -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}' \
    --max-time 30 2>/dev/null || echo "")

  # Parse SSE if needed
  if echo "$LIVE_RESPONSE" | grep -q '^data: '; then
    LIVE_RESPONSE=$(echo "$LIVE_RESPONSE" | grep '^data: ' | tail -1 | sed 's/^data: //')
  fi

  LIVE_TOOLS=$(echo "$LIVE_RESPONSE" | jq -r '.result.tools[].name' 2>/dev/null | sort)

  # Get YAML tools
  YAML_TOOLS=$(python3 -c "
import yaml, sys
with open('${VS_FILE}') as f:
    d = yaml.safe_load(f)
tools = d.get('spec',{}).get('tools',[])
for t in sorted(tools):
    print(t)
")

  if [ "$LIVE_TOOLS" != "$YAML_TOOLS" ]; then
    echo "DRIFT DETECTED in ${VS_NAME}: live gateway tool names do not match ${VS_FILE}'s spec.tools list"
    diff <(echo "$YAML_TOOLS") <(echo "$LIVE_TOOLS") || true
    DRIFT_FOUND=1
  else
    LIVE_COUNT=$(echo "$LIVE_TOOLS" | wc -l | tr -d ' ')
    echo "OK: ${VS_NAME} tool list matches live gateway exactly ($LIVE_COUNT tools)"
  fi
done

if [ "$DRIFT_FOUND" -eq 1 ]; then
  echo ""
  echo "FAIL: one or more virtual servers have drifted tool lists"
  exit 1
else
  echo ""
  echo "PASS: all 4 virtual servers match live gateway exactly"
  exit 0
fi
