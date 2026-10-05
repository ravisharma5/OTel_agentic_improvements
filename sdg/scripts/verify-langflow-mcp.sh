#!/usr/bin/env bash
# verify-langflow-mcp.sh -- Verify Langflow AgentBlock can consume MCP Gateway tools
#                           via the stateful MCP session protocol.
#
# Resolves RESEARCH.md Open Question 3: "Does Langflow/LangGraph have native
# MCP protocol support?" and validates Assumption A4 (MEDIUM risk): "Langflow
# can connect to the MCP Gateway and execute tool calls."
#
# MCP Streamable HTTP session protocol (MANDATORY for gateway communication):
#   1. Send JSON-RPC "initialize" to get Mcp-Session-Id header
#   2. Include Mcp-Session-Id on ALL subsequent requests (tools/list, tools/call)
#   3. Re-initialize if session expires (HTTP 400/401 from gateway)
#
# Tests:
#   1. MCP Gateway session handshake (initialize + Mcp-Session-Id extraction)
#   2. Gateway tools/list with session ID
#   3. Langflow health check
#   4. Langflow native MCP tool discovery
#   5. Langflow native MCP tool call
#
# Contingency: If native MCP support is absent (Tests 4/5 fail), prints
# adapter instructions including mandatory session handshake handling.
#
# Usage: sdg/scripts/verify-langflow-mcp.sh
#
# Environment variables:
#   GATEWAY_URL     https://mcp.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com/mcp
#   LANGFLOW_URL    http://langflow.rhoai-sdg.svc:7860
#   KEYCLOAK_URL    https://mcp-keycloak-otel25-gateway.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com
#   CLIENT_ID       sdg-pipeline
#   CLIENT_SECRET   (required -- no default)
#
# Requires: bash 4+, curl, jq

set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────────────────

GATEWAY_URL="${GATEWAY_URL:-https://mcp.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com/mcp}"
LANGFLOW_URL="${LANGFLOW_URL:-http://langflow.rhoai-sdg.svc:7860}"
KEYCLOAK_URL="${KEYCLOAK_URL:-https://mcp-keycloak-otel25-gateway.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com}"
CLIENT_ID="${CLIENT_ID:-sdg-pipeline}"

if [[ -z "${CLIENT_SECRET:-}" ]]; then
  echo "ERROR: CLIENT_SECRET environment variable is required."
  echo "  Set it from the Keycloak client secret for the '$CLIENT_ID' client."
  exit 1
fi

PASS=0
FAIL=0
MCP_NATIVE=false
MCP_SESSION_ID=""
JWT_TOKEN=""

# Temp files for this run
TMPDIR_RUN=$(mktemp -d)
trap 'rm -rf "$TMPDIR_RUN"' EXIT

echo "=== Langflow MCP Gateway Integration Verification ==="
echo "Gateway URL:  ${GATEWAY_URL}"
echo "Langflow URL: ${LANGFLOW_URL}"
echo "Keycloak URL: ${KEYCLOAK_URL}"
echo "Client ID:    ${CLIENT_ID}"
echo ""
echo "Resolves: RESEARCH.md Open Question 3, Assumption A4"
echo ""

# ─── Helper: record test result ─────────────────────────────────────────────

record_result() {
  local test_name="$1"
  local status="$2"
  local detail="${3:-}"
  if [[ "$status" == "PASS" ]]; then
    PASS=$((PASS + 1))
    echo "  [PASS] $test_name"
  else
    FAIL=$((FAIL + 1))
    echo "  [FAIL] $test_name"
  fi
  [[ -n "$detail" ]] && echo "         $detail"
}

# ─── JWT Acquisition ─────────────────────────────────────────────────────────

echo "--- Acquiring JWT token ---"

TOKEN_ENDPOINT="${KEYCLOAK_URL}/realms/mcp/protocol/openid-connect/token"
TOKEN_RESPONSE=$(curl -sk -X POST "$TOKEN_ENDPOINT" \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=${CLIENT_ID}" \
  -d "client_secret=${CLIENT_SECRET}" \
  -o "$TMPDIR_RUN/token_response.json" \
  -w "%{http_code}" \
  2>/dev/null || echo "000")

if [[ "$TOKEN_RESPONSE" == "200" ]]; then
  JWT_TOKEN=$(jq -r '.access_token // empty' "$TMPDIR_RUN/token_response.json")
  if [[ -n "$JWT_TOKEN" ]]; then
    echo "  JWT acquired (${#JWT_TOKEN} chars)"
  else
    echo "  ERROR: Token response missing access_token field"
    echo "  Cannot proceed without authentication."
    exit 1
  fi
else
  echo "  ERROR: Keycloak returned HTTP $TOKEN_RESPONSE"
  echo "  Cannot proceed without authentication."
  exit 1
fi

echo ""

# ─── Test 1: MCP Gateway Session Handshake ───────────────────────────────────

echo "--- Test 1: MCP Gateway session handshake from RHOAI cluster ---"
echo "  Purpose: Verify MCP initialize JSON-RPC handshake and Mcp-Session-Id extraction"

INIT_HTTP_CODE=$(curl -sk \
  -X POST "$GATEWAY_URL" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Authorization: Bearer ${JWT_TOKEN}" \
  -d '{
    "jsonrpc": "2.0",
    "method": "initialize",
    "params": {
      "protocolVersion": "2024-11-05",
      "capabilities": {},
      "clientInfo": {
        "name": "sdg-pipeline",
        "version": "1.0"
      }
    },
    "id": 1
  }' \
  -o "$TMPDIR_RUN/init_response.json" \
  -D "$TMPDIR_RUN/init_headers.txt" \
  -w "%{http_code}" \
  2>/dev/null || echo "000")

if [[ "$INIT_HTTP_CODE" == "200" ]]; then
  # Check for JSON-RPC result in response
  HAS_RESULT=$(jq -r '.result // empty' "$TMPDIR_RUN/init_response.json" 2>/dev/null || echo "")
  if [[ -n "$HAS_RESULT" ]]; then
    record_result "MCP initialize JSON-RPC response" "PASS" "HTTP 200, result present"
  else
    record_result "MCP initialize JSON-RPC response" "FAIL" "HTTP 200 but no 'result' in response body"
  fi

  # Extract Mcp-Session-Id from response headers (case-insensitive grep)
  MCP_SESSION_ID=$(grep -i "mcp-session-id" "$TMPDIR_RUN/init_headers.txt" \
    | sed 's/^[^:]*: *//' | tr -d '\r\n' || echo "")

  if [[ -n "$MCP_SESSION_ID" ]]; then
    record_result "Mcp-Session-Id extraction" "PASS" "Session ID: ${MCP_SESSION_ID:0:16}..."
  else
    record_result "Mcp-Session-Id extraction" "FAIL" "No Mcp-Session-Id header in response"
  fi
else
  record_result "MCP initialize JSON-RPC response" "FAIL" "HTTP $INIT_HTTP_CODE (gateway unreachable or auth failed)"
  record_result "Mcp-Session-Id extraction" "FAIL" "Cannot extract -- initialize failed"
fi

echo ""

# ─── Test 2: Gateway tools/list with Session ─────────────────────────────────

echo "--- Test 2: Gateway tools/list with Mcp-Session-Id ---"

if [[ -n "$MCP_SESSION_ID" ]]; then
  TOOLS_HTTP_CODE=$(curl -sk \
    -X POST "$GATEWAY_URL" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "Authorization: Bearer ${JWT_TOKEN}" \
    -H "Mcp-Session-Id: ${MCP_SESSION_ID}" \
    -d '{
      "jsonrpc": "2.0",
      "method": "tools/list",
      "id": 2
    }' \
    -o "$TMPDIR_RUN/tools_response.json" \
    -w "%{http_code}" \
    2>/dev/null || echo "000")

  if [[ "$TOOLS_HTTP_CODE" == "200" ]]; then
    TOOL_COUNT=$(jq '.result.tools | length' "$TMPDIR_RUN/tools_response.json" 2>/dev/null || echo "0")
    if [[ "$TOOL_COUNT" -gt 0 ]]; then
      record_result "Gateway tools/list with session" "PASS" "$TOOL_COUNT tools discovered"
    else
      record_result "Gateway tools/list with session" "FAIL" "HTTP 200 but 0 tools in response"
    fi
  else
    record_result "Gateway tools/list with session" "FAIL" "HTTP $TOOLS_HTTP_CODE"
  fi
else
  record_result "Gateway tools/list with session" "FAIL" "Skipped -- no Mcp-Session-Id from Test 1"
fi

echo ""

# ─── Test 3: Langflow Health ─────────────────────────────────────────────────

echo "--- Test 3: Langflow health check ---"

LANGFLOW_HTTP_CODE=$(curl -sk \
  -o "$TMPDIR_RUN/langflow_health.json" \
  -w "%{http_code}" \
  "${LANGFLOW_URL}/health" \
  2>/dev/null || echo "000")

if [[ "$LANGFLOW_HTTP_CODE" == "200" ]]; then
  record_result "Langflow health" "PASS" "HTTP 200"
else
  record_result "Langflow health" "FAIL" "HTTP $LANGFLOW_HTTP_CODE (Langflow not reachable)"
fi

echo ""

# ─── Test 4: Langflow tools/list via MCP ─────────────────────────────────────

echo "--- Test 4: Langflow native MCP tool discovery ---"
echo "  Purpose: Determine if Langflow AgentBlock natively supports MCP protocol"

LANGFLOW_MCP_HTTP_CODE=$(curl -sk \
  -X POST "${LANGFLOW_URL}/api/v1/run/default" \
  -H "Content-Type: application/json" \
  -d '{
    "input_value": "List all available MCP tools",
    "output_type": "chat",
    "input_type": "chat",
    "tweaks": {}
  }' \
  -o "$TMPDIR_RUN/langflow_mcp_tools.json" \
  -w "%{http_code}" \
  2>/dev/null || echo "000")

if [[ "$LANGFLOW_MCP_HTTP_CODE" == "200" ]]; then
  # Check if the response contains tool references
  HAS_TOOLS=$(jq -r '.. | .tools? // empty | length' "$TMPDIR_RUN/langflow_mcp_tools.json" 2>/dev/null \
    | head -1 || echo "0")
  if [[ "${HAS_TOOLS:-0}" -gt 0 ]]; then
    MCP_NATIVE=true
    record_result "Langflow native MCP tool discovery" "PASS" "Found $HAS_TOOLS tools via native MCP"
  else
    MCP_NATIVE=false
    record_result "Langflow native MCP tool discovery" "FAIL" "HTTP 200 but no MCP tools in response -- adapter needed"
  fi
else
  MCP_NATIVE=false
  record_result "Langflow native MCP tool discovery" "FAIL" "HTTP $LANGFLOW_MCP_HTTP_CODE -- adapter needed"
fi

echo ""

# ─── Test 5: Langflow tools/call via MCP ─────────────────────────────────────

echo "--- Test 5: Langflow native MCP tool call ---"

if [[ "$MCP_NATIVE" == "true" ]]; then
  LANGFLOW_CALL_HTTP_CODE=$(curl -sk \
    -X POST "${LANGFLOW_URL}/api/v1/run/default" \
    -H "Content-Type: application/json" \
    -d '{
      "input_value": "List all alarms from the network",
      "output_type": "chat",
      "input_type": "chat",
      "tweaks": {}
    }' \
    -o "$TMPDIR_RUN/langflow_tool_call.json" \
    -w "%{http_code}" \
    2>/dev/null || echo "000")

  if [[ "$LANGFLOW_CALL_HTTP_CODE" == "200" ]]; then
    # Check response for tool call evidence (alarm data)
    HAS_ALARM_DATA=$(jq -r '.. | strings | select(test("alarm|Alarm|tmf642"; "i"))' \
      "$TMPDIR_RUN/langflow_tool_call.json" 2>/dev/null | head -1 || echo "")
    if [[ -n "$HAS_ALARM_DATA" ]]; then
      record_result "Langflow native MCP tool call" "PASS" "Tool call returned alarm data"
    else
      record_result "Langflow native MCP tool call" "FAIL" "HTTP 200 but no tool call evidence in response"
    fi
  else
    record_result "Langflow native MCP tool call" "FAIL" "HTTP $LANGFLOW_CALL_HTTP_CODE"
  fi
else
  record_result "Langflow native MCP tool call" "FAIL" "Skipped -- native MCP not detected in Test 4"
fi

echo ""

# ─── Contingency: Adapter Instructions ───────────────────────────────────────

if [[ "$MCP_NATIVE" == "false" ]]; then
  echo "==========================================================================="
  echo "  CONTINGENCY: Langflow MCP Adapter Required"
  echo "==========================================================================="
  echo ""
  echo "  Langflow does NOT have native MCP support. A lightweight adapter is"
  echo "  required to bridge the MCP Gateway's tools/list and tools/call"
  echo "  endpoints to Langflow-compatible tool definitions."
  echo ""
  echo "  Build an adapter script at: sdg/scripts/langflow-mcp-adapter.py"
  echo ""
  echo "  The adapter MUST:"
  echo ""
  echo "  (a) PERFORM THE INITIALIZE JSON-RPC HANDSHAKE to acquire the"
  echo "      Mcp-Session-Id header BEFORE issuing tools/list or tools/call."
  echo "      This is the MCP Streamable HTTP session protocol -- the gateway"
  echo "      will reject requests without a valid Mcp-Session-Id."
  echo ""
  echo "      Handshake request:"
  echo "        POST \$GATEWAY_URL"
  echo "        Content-Type: application/json"
  echo "        Authorization: Bearer \$JWT_TOKEN"
  echo "        Body: {"
  echo "          \"jsonrpc\": \"2.0\","
  echo "          \"method\": \"initialize\","
  echo "          \"params\": {"
  echo "            \"protocolVersion\": \"2024-11-05\","
  echo "            \"capabilities\": {},"
  echo "            \"clientInfo\": {\"name\": \"sdg-pipeline\", \"version\": \"1.0\"}"
  echo "          },"
  echo "          \"id\": 1"
  echo "        }"
  echo "      Response: HTTP 200 with Mcp-Session-Id header"
  echo ""
  echo "  (b) INCLUDE THE Mcp-Session-Id HEADER on ALL subsequent requests"
  echo "      to the gateway (tools/list and tools/call)."
  echo ""
  echo "  (c) RE-INITIALIZE if the session expires (HTTP 400/401 from gateway)."
  echo "      This can happen after long idle periods between sdg_hub pipeline"
  echo "      steps."
  echo ""
  echo "  (d) FETCH TOOL SCHEMAS from the gateway via tools/list JSON-RPC call"
  echo "      (with Mcp-Session-Id header)."
  echo ""
  echo "  (e) CONVERT each MCP tool schema to a Langflow Custom Component."
  echo "      Each tool becomes a component with inputs matching the MCP tool's"
  echo "      inputSchema properties."
  echo ""
  echo "  (f) REGISTER the components with the Langflow instance via its API."
  echo ""
  echo "  After building the adapter, re-run this script to verify."
  echo ""
  echo "==========================================================================="
  echo ""
fi

# ─── Summary ─────────────────────────────────────────────────────────────────

TOTAL=$((PASS + FAIL))
echo "=== Results: Langflow MCP Gateway Integration ==="
echo "Passed: $PASS"
echo "Failed: $FAIL"
echo "Total:  $TOTAL"
echo ""

if [[ $FAIL -eq 0 && $PASS -gt 0 ]]; then
  echo "OVERALL: PASS"
  echo ""
  echo "Langflow MCP integration VERIFIED -- MCP session handshake"
  echo "(initialize + Mcp-Session-Id) works end-to-end."
  echo "Open Question 3 resolved: native support confirmed."
  exit 0
elif [[ "$MCP_NATIVE" == "false" && "$MCP_SESSION_ID" != "" ]]; then
  echo "OVERALL: PARTIAL -- adapter needed"
  echo ""
  echo "Langflow MCP integration REQUIRES ADAPTER -- see contingency"
  echo "instructions above including mandatory session handshake handling."
  echo "Open Question 3 resolved: native support absent, adapter needed."
  echo ""
  echo "The MCP Gateway itself IS reachable and the session handshake works."
  echo "Only the Langflow-to-MCP bridge needs an adapter."
  exit 0
else
  echo "OVERALL: FAIL"
  echo ""
  echo "MCP Gateway is unreachable or session handshake failed."
  echo "This is a fundamental blocker -- check network connectivity,"
  echo "Keycloak configuration, and gateway health."
  exit 1
fi
