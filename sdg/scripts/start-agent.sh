#!/usr/bin/env bash
# start-agent.sh -- Start Langflow agent wrapping MCP Gateway tools for sdg_hub
#
# Acquires a JWT token from the existing Keycloak instance (D-07: reuse Phase 3's
# client-credentials flow, no new auth infrastructure) and starts a Langflow
# instance configured to proxy MCP Gateway tools for sdg_hub's AgentBlock.
#
# The Langflow flow must be pre-configured to:
#   1. Use the MCP Gateway's tools/list endpoint to discover available tools
#   2. Use the MCP Gateway's tools/call endpoint to invoke tools
#   3. Pass the JWT in the Authorization: Bearer header on all gateway requests
#   4. Perform the MCP initialize handshake to acquire Mcp-Session-Id before
#      calling tools/list or tools/call
#
# Usage: sdg/scripts/start-agent.sh [--dry-run]
#   --dry-run : Print configuration and test JWT acquisition without starting Langflow
#
# Environment variables (defaults shown where applicable):
#   GATEWAY_URL     https://mcp.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com/mcp
#   KEYCLOAK_URL    https://mcp-keycloak-otel25-gateway.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com
#   CLIENT_ID       sdg-pipeline
#   CLIENT_SECRET   (required -- no default; set via env or k8s secret)
#   LANGFLOW_PORT   7860
#
# References:
#   - D-06: Pipeline runs on separate OpenShift AI (RHOAI) cluster
#   - D-07: Reuse existing Keycloak client-credentials flow for cross-cluster auth
#   - gateway/openshift/auth-policy.yaml: JWT issuer URL and auth requirements
#
# Requires: bash 4+, curl, jq, python3, langflow

set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────────────────

GATEWAY_URL="${GATEWAY_URL:-https://mcp.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com/mcp}"
KEYCLOAK_URL="${KEYCLOAK_URL:-https://mcp-keycloak-otel25-gateway.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com}"
CLIENT_ID="${CLIENT_ID:-sdg-pipeline}"
LANGFLOW_PORT="${LANGFLOW_PORT:-7860}"
DRY_RUN=false

# CLIENT_SECRET must be set -- no hardcoded default (T-04-04 threat mitigation)
if [[ -z "${CLIENT_SECRET:-}" ]]; then
  echo "ERROR: CLIENT_SECRET environment variable is required."
  echo "  Set it from the Keycloak client secret for the '$CLIENT_ID' client."
  echo "  On OpenShift: export CLIENT_SECRET=\$(oc get secret keycloak-client-secret-mcp-gateway \\"
  echo "    -n otel25-gateway -o jsonpath='{.data.CLIENT_SECRET}' | base64 -d)"
  exit 1
fi

# ─── Argument Parsing ────────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dry-run)
      DRY_RUN=true
      shift
      ;;
    -h|--help)
      echo "Usage: $0 [--dry-run]"
      echo "  --dry-run : Test JWT acquisition and print config without starting Langflow"
      exit 0
      ;;
    *)
      echo "ERROR: Unknown argument '$1'. Use --help for usage."
      exit 1
      ;;
  esac
done

# ─── JWT Acquisition ─────────────────────────────────────────────────────────

TOKEN_ENDPOINT="${KEYCLOAK_URL}/realms/mcp/protocol/openid-connect/token"

echo "=== Langflow Agent Startup ==="
echo "Gateway URL:   $GATEWAY_URL"
echo "Keycloak URL:  $KEYCLOAK_URL"
echo "Client ID:     $CLIENT_ID"
echo "Langflow port: $LANGFLOW_PORT"
echo ""
echo "--- Acquiring JWT token via client_credentials grant ---"

TOKEN_RESPONSE=$(curl -sk -X POST "$TOKEN_ENDPOINT" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=${CLIENT_ID}" \
  -d "client_secret=${CLIENT_SECRET}" \
  2>/dev/null)

JWT_TOKEN=$(echo "$TOKEN_RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    token = data.get('access_token', '')
    if not token:
        error = data.get('error_description', data.get('error', 'unknown error'))
        print(f'ERROR: {error}', file=sys.stderr)
        sys.exit(1)
    print(token)
except (json.JSONDecodeError, KeyError) as e:
    print(f'ERROR: Failed to parse token response: {e}', file=sys.stderr)
    sys.exit(1)
")

if [[ -z "$JWT_TOKEN" ]]; then
  echo "ERROR: Failed to acquire JWT token from Keycloak."
  echo "  Check CLIENT_SECRET and KEYCLOAK_URL."
  exit 1
fi

echo "JWT token acquired successfully (${#JWT_TOKEN} chars)"

# ─── Dry Run Mode ────────────────────────────────────────────────────────────

if [[ "$DRY_RUN" == "true" ]]; then
  echo ""
  echo "--- Dry Run: Testing MCP Gateway reachability ---"
  HTTP_CODE=$(curl -sk -o /dev/null -w "%{http_code}" \
    -X POST "$GATEWAY_URL" \
    -H "Content-Type: application/json" \
    -H "Authorization: Bearer ${JWT_TOKEN}" \
    -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"sdg-pipeline","version":"1.0"}},"id":1}' \
    2>/dev/null || echo "000")

  if [[ "$HTTP_CODE" == "200" ]]; then
    echo "MCP Gateway reachable (HTTP $HTTP_CODE) -- ready for Langflow"
  else
    echo "WARNING: MCP Gateway returned HTTP $HTTP_CODE (may not be reachable from this cluster)"
  fi

  echo ""
  echo "--- Dry Run Complete ---"
  echo "Configuration verified. Run without --dry-run to start Langflow."
  exit 0
fi

# ─── Start Langflow ──────────────────────────────────────────────────────────

echo ""
echo "--- Starting Langflow ---"
echo "The Langflow flow must be pre-configured to use the MCP Gateway at:"
echo "  $GATEWAY_URL"
echo ""
echo "Environment variables passed to Langflow:"
echo "  MCP_GATEWAY_URL=$GATEWAY_URL"
echo "  MCP_GATEWAY_JWT=$JWT_TOKEN (first 20 chars: ${JWT_TOKEN:0:20}...)"
echo ""

# Export gateway configuration for Langflow's MCP tool provider
export MCP_GATEWAY_URL="$GATEWAY_URL"
export MCP_GATEWAY_JWT="$JWT_TOKEN"

exec langflow run \
  --host 0.0.0.0 \
  --port "$LANGFLOW_PORT"
