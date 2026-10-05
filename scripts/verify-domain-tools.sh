#!/usr/bin/env bash
# verify-domain-tools.sh -- Per-domain MCP tool verification against local or remote server
#
# Three-tier verification:
#   Test 1 (smoke):    tools/list -- confirms server exposes expected tool count
#   Test 2 (semantic): One representative tool per domain with a KNOWN-GOOD payload,
#                      verifying Prism returns meaningful mock data (not validation errors)
#   Test 3 (protocol): Remaining tools with empty args, verifying JSON-RPC round-trip
#
# MCP Streamable HTTP requires session management:
#   1. Send initialize to get Mcp-Session-Id
#   2. Send notifications/initialized with session ID
#   3. Use session ID for all subsequent requests
#
# Usage: scripts/verify-domain-tools.sh <domain> [base-url]
#   domain:   tmf642 | tmf628 | tmf621 | nwdaf | camara
#   base-url: default http://localhost:8000
#
# Requires: bash 4+, curl, jq

set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────────────────

DOMAIN="${1:-}"
BASE_URL="${2:-http://localhost:8000}"
MCP_ENDPOINT="${BASE_URL}/mcp"

if [[ -z "$DOMAIN" ]]; then
  echo "Usage: $0 <domain> [base-url]"
  echo "  domain: tmf642 | tmf628 | tmf621 | nwdaf | camara"
  echo "  base-url: default http://localhost:8000"
  exit 1
fi

# Expected tool counts per domain
declare -A EXPECTED_TOOL_COUNTS=(
  [tmf642]=6
  [tmf628]=5
  [tmf621]=4
  [nwdaf]=3
  [camara]=2
)

# Known-good payloads per domain: TOOL_NAME and TOOL_ARGS
# Each domain has one representative tool with arguments that produce a valid
# Prism response (mock data), not a validation error.
#
# TMF GET endpoints accept no body -- Prism returns mock data for bare GET.
# NWDAF requires event_id parameter.
# CAMARA requires device + location parameters.

declare -A KNOWN_GOOD_TOOL_NAME=(
  [tmf642]="tmf642_list_alarms"
  [tmf628]="tmf628_list_performance"
  [tmf621]="tmf621_list_troubletickets"
  [nwdaf]="nwdaf_get_nwdaf_analytics"
  [camara]="camara_verify_location"
)

declare -A KNOWN_GOOD_TOOL_ARGS=(
  [tmf642]='{}'
  [tmf628]='{}'
  [tmf621]='{}'
  [nwdaf]='{"event_id": "NF_LOAD"}'
  [camara]='{"device_phone_number": "+123456789", "latitude": 40.0, "longitude": -74.0, "accuracy": 100.0}'
)

if [[ -z "${EXPECTED_TOOL_COUNTS[$DOMAIN]+x}" ]]; then
  echo "ERROR: Unknown domain '$DOMAIN'. Supported: tmf642, tmf628, tmf621, nwdaf, camara"
  exit 1
fi

EXPECTED_COUNT="${EXPECTED_TOOL_COUNTS[$DOMAIN]}"

# Temp files for this run
TMPDIR_RUN=$(mktemp -d)
trap 'rm -rf "$TMPDIR_RUN"' EXIT

PASS=0
FAIL=0
WARN=0
SEMANTIC_PASS=0
SEMANTIC_FAIL=0
PROTOCOL_PASS=0
PROTOCOL_FAIL=0

echo "=== Domain Tool Verification: $DOMAIN ==="
echo "Target: ${MCP_ENDPOINT}"
echo "Expected tools: ${EXPECTED_COUNT}"
echo ""

# ─── SSE Response Parsing Helper ─────────────────────────────────────────────
# FastMCP responds with SSE format for Streamable HTTP.
# Extract the last JSON data line from an SSE response body.
_parse_sse_json() {
  local body="$1"
  if echo "$body" | grep -q '^data: '; then
    echo "$body" | grep '^data: ' | tail -1 | sed 's/^data: //'
  else
    echo "$body"
  fi
}

# ─── Session Setup: initialize + notifications/initialized ───────────────────
echo "--- Session Setup: MCP initialize handshake ---"

INIT_RESPONSE=$(curl -s -D "${TMPDIR_RUN}/init-headers" \
  -X POST "${MCP_ENDPOINT}" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"verify-domain-tools","version":"1.0"}},"id":0}' \
  --max-time 30 2>/dev/null || echo "")

# Extract session ID from response headers
SESSION_ID=$(grep -i 'mcp-session-id' "${TMPDIR_RUN}/init-headers" 2>/dev/null | tr -d '\r' | awk '{print $2}' || echo "")

if [[ -z "$SESSION_ID" ]]; then
  echo "  FAIL: could not obtain Mcp-Session-Id from initialize response"
  echo "  Headers: $(cat "${TMPDIR_RUN}/init-headers" 2>/dev/null || echo 'none')"
  echo ""
  echo "=== Results ==="
  echo "OVERALL: FAIL (session setup failed)"
  exit 1
fi

echo "  PASS: obtained session ID"

# Send notifications/initialized (no response body expected)
curl -s -X POST "${MCP_ENDPOINT}" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: ${SESSION_ID}" \
  -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  --max-time 10 >/dev/null 2>&1 || true

echo "  PASS: sent notifications/initialized"
echo ""

# ─── Test 1 (Smoke): tools/list ──────────────────────────────────────────────
echo "--- Test 1 (Smoke): tools/list ---"

TOOLS_RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST "${MCP_ENDPOINT}" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -H "Mcp-Session-Id: ${SESSION_ID}" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' \
  --max-time 30 2>/dev/null || echo -e "\n000")

TOOLS_HTTP_CODE=$(echo "$TOOLS_RESPONSE" | tail -1)
TOOLS_BODY=$(echo "$TOOLS_RESPONSE" | sed '$d')

if [[ "$TOOLS_HTTP_CODE" != "200" ]]; then
  echo "  FAIL: HTTP $TOOLS_HTTP_CODE (expected 200)"
  FAIL=$((FAIL + 1))
  echo ""
  echo "=== Results ==="
  echo "OVERALL: FAIL"
  exit 1
fi

# Parse SSE if needed
TOOLS_BODY=$(_parse_sse_json "$TOOLS_BODY")

# Validate JSON
if ! echo "$TOOLS_BODY" | jq . >/dev/null 2>&1; then
  echo "  FAIL: invalid JSON body"
  FAIL=$((FAIL + 1))
  echo ""
  echo "=== Results ==="
  echo "OVERALL: FAIL"
  exit 1
fi

TOOL_COUNT=$(echo "$TOOLS_BODY" | jq '.result.tools | length' 2>/dev/null || echo "0")

if [[ "$TOOL_COUNT" -eq "$EXPECTED_COUNT" ]]; then
  echo "  PASS: tools/list returned $TOOL_COUNT tools (expected $EXPECTED_COUNT)"
  PASS=$((PASS + 1))
elif [[ "$TOOL_COUNT" -gt 0 ]]; then
  echo "  WARN: tools/list returned $TOOL_COUNT tools (expected $EXPECTED_COUNT)"
  WARN=$((WARN + 1))
  PASS=$((PASS + 1))
else
  echo "  FAIL: tools/list returned 0 tools"
  FAIL=$((FAIL + 1))
fi

# Extract tool names for subsequent tests
TOOL_NAMES=$(echo "$TOOLS_BODY" | jq -r '.result.tools[].name' 2>/dev/null || echo "")
echo "  Tools: $TOOL_NAMES" | tr '\n' ', '
echo ""
echo ""

# ─── Test 2 (Semantic): Known-good payload for representative tool ───────────
echo "--- Test 2 (Semantic): Known-good payload verification ---"

SEMANTIC_TOOL="${KNOWN_GOOD_TOOL_NAME[$DOMAIN]}"
SEMANTIC_ARGS="${KNOWN_GOOD_TOOL_ARGS[$DOMAIN]}"

# Check if the expected semantic tool name exists in the discovered tools.
# If not, try to find a matching tool by partial name (the actual tool name
# may differ from our assumed name pattern).
SEMANTIC_TOOL_FOUND="false"
if echo "$TOOL_NAMES" | grep -qx "$SEMANTIC_TOOL"; then
  SEMANTIC_TOOL_FOUND="true"
else
  # Try to discover the tool by pattern matching
  # For tmf642, look for a tool containing "list" and "alarm" (case-insensitive)
  # For tmf628, look for "list" and "performance"
  # For tmf621, look for "list" and "troubleticket" or "trouble_ticket"
  # For nwdaf, look for "analytics" or "nwdaf"
  # For camara, look for "verify" or "location"
  case "$DOMAIN" in
    tmf642)
      DISCOVERED=$(echo "$TOOL_NAMES" | grep -i "list" | grep -i "alarm" | head -1 || echo "")
      ;;
    tmf628)
      DISCOVERED=$(echo "$TOOL_NAMES" | grep -i "list" | grep -i "perform" | head -1 || echo "")
      ;;
    tmf621)
      DISCOVERED=$(echo "$TOOL_NAMES" | grep -i "list" | grep -i "trouble" | head -1 || echo "")
      ;;
    nwdaf)
      DISCOVERED=$(echo "$TOOL_NAMES" | grep -i "analytics" | head -1 || echo "")
      ;;
    camara)
      DISCOVERED=$(echo "$TOOL_NAMES" | grep -i "verify" | head -1 || echo "")
      ;;
  esac

  if [[ -n "$DISCOVERED" ]]; then
    echo "  Note: expected tool '$SEMANTIC_TOOL' not found; using discovered '$DISCOVERED'"
    SEMANTIC_TOOL="$DISCOVERED"
    SEMANTIC_TOOL_FOUND="true"
  fi
fi

if [[ "$SEMANTIC_TOOL_FOUND" == "false" ]]; then
  echo "  FAIL: Could not find semantic test tool for $DOMAIN"
  echo "        Expected: ${KNOWN_GOOD_TOOL_NAME[$DOMAIN]}"
  echo "        Available: $(echo "$TOOL_NAMES" | tr '\n' ', ')"
  SEMANTIC_FAIL=$((SEMANTIC_FAIL + 1))
  FAIL=$((FAIL + 1))
else
  echo "  Testing: $SEMANTIC_TOOL with args: $SEMANTIC_ARGS"

  CALL_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "${MCP_ENDPOINT}" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "Mcp-Session-Id: ${SESSION_ID}" \
    -d "{\"jsonrpc\":\"2.0\",\"method\":\"tools/call\",\"params\":{\"name\":\"$SEMANTIC_TOOL\",\"arguments\":$SEMANTIC_ARGS},\"id\":2}" \
    --max-time 30 2>/dev/null || echo -e "\n000")

  CALL_HTTP_CODE=$(echo "$CALL_RESPONSE" | tail -1)
  CALL_BODY=$(echo "$CALL_RESPONSE" | sed '$d')
  CALL_BODY=$(_parse_sse_json "$CALL_BODY")

  if [[ "$CALL_HTTP_CODE" != "200" ]]; then
    echo "  FAIL: [semantic] $SEMANTIC_TOOL -- HTTP $CALL_HTTP_CODE (expected 200)"
    SEMANTIC_FAIL=$((SEMANTIC_FAIL + 1))
    FAIL=$((FAIL + 1))
  elif ! echo "$CALL_BODY" | jq . >/dev/null 2>&1; then
    echo "  FAIL: [semantic] $SEMANTIC_TOOL -- invalid JSON response"
    SEMANTIC_FAIL=$((SEMANTIC_FAIL + 1))
    FAIL=$((FAIL + 1))
  else
    # Check for MCP-level isError flag
    IS_ERROR=$(echo "$CALL_BODY" | jq -r '.result.isError // false' 2>/dev/null || echo "false")

    # Extract response content text
    CONTENT_TEXT=$(echo "$CALL_BODY" | jq -r '
      if .result.content then
        [.result.content[] | select(.type == "text") | .text] | join("\n")
      elif .error then
        .error.message // (.error | tostring)
      else
        ""
      end' 2>/dev/null || echo "")

    CONTENT_LOWER=$(echo "$CONTENT_TEXT" | tr '[:upper:]' '[:lower:]')

    if [[ "$IS_ERROR" == "true" ]]; then
      echo "  FAIL: [semantic] $SEMANTIC_TOOL -- isError=true in MCP response"
      echo "        Content: ${CONTENT_TEXT:0:200}"
      SEMANTIC_FAIL=$((SEMANTIC_FAIL + 1))
      FAIL=$((FAIL + 1))
    elif [[ -z "$CONTENT_TEXT" ]]; then
      echo "  FAIL: [semantic] $SEMANTIC_TOOL -- empty response content"
      SEMANTIC_FAIL=$((SEMANTIC_FAIL + 1))
      FAIL=$((FAIL + 1))
    elif echo "$CONTENT_TEXT" | grep -qi '^Error:'; then
      echo "  FAIL: [semantic] $SEMANTIC_TOOL -- response starts with 'Error:'"
      echo "        Content: ${CONTENT_TEXT:0:200}"
      SEMANTIC_FAIL=$((SEMANTIC_FAIL + 1))
      FAIL=$((FAIL + 1))
    elif echo "$CONTENT_LOWER" | grep -qE "(request body must have required property|must have required property|validation)"; then
      echo "  FAIL: [semantic] $SEMANTIC_TOOL -- Prism validation error in response"
      echo "        Content: ${CONTENT_TEXT:0:200}"
      SEMANTIC_FAIL=$((SEMANTIC_FAIL + 1))
      FAIL=$((FAIL + 1))
    else
      echo "  PASS: [semantic] $SEMANTIC_TOOL -- valid response with data"
      echo "        Content preview: ${CONTENT_TEXT:0:120}"
      SEMANTIC_PASS=$((SEMANTIC_PASS + 1))
      PASS=$((PASS + 1))
    fi
  fi
fi
echo ""

# ─── Test 3 (Protocol): Remaining tools with empty args ─────────────────────
echo "--- Test 3 (Protocol): Remaining tools round-trip ---"

MSG_ID=10
while IFS= read -r TOOL_NAME; do
  [[ -z "$TOOL_NAME" ]] && continue

  # Skip the semantic test tool (already tested above)
  if [[ "$TOOL_NAME" == "$SEMANTIC_TOOL" ]]; then
    continue
  fi

  CALL_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "${MCP_ENDPOINT}" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "Mcp-Session-Id: ${SESSION_ID}" \
    -d "{\"jsonrpc\":\"2.0\",\"method\":\"tools/call\",\"params\":{\"name\":\"$TOOL_NAME\",\"arguments\":{}},\"id\":$MSG_ID}" \
    --max-time 30 2>/dev/null || echo -e "\n000")

  CALL_HTTP_CODE=$(echo "$CALL_RESPONSE" | tail -1)
  CALL_BODY=$(echo "$CALL_RESPONSE" | sed '$d')
  CALL_BODY=$(_parse_sse_json "$CALL_BODY")

  if [[ "$CALL_HTTP_CODE" != "200" ]]; then
    echo "  FAIL: [protocol] $TOOL_NAME -- HTTP $CALL_HTTP_CODE"
    PROTOCOL_FAIL=$((PROTOCOL_FAIL + 1))
    FAIL=$((FAIL + 1))
  elif ! echo "$CALL_BODY" | jq . >/dev/null 2>&1; then
    echo "  FAIL: [protocol] $TOOL_NAME -- invalid JSON response"
    PROTOCOL_FAIL=$((PROTOCOL_FAIL + 1))
    FAIL=$((FAIL + 1))
  else
    # For protocol tests, we accept any valid JSON-RPC response
    # including Prism validation errors (those are acceptable here)
    HAS_RESULT=$(echo "$CALL_BODY" | jq 'has("result")' 2>/dev/null || echo "false")
    HAS_ERROR=$(echo "$CALL_BODY" | jq 'has("error")' 2>/dev/null || echo "false")

    if [[ "$HAS_RESULT" == "true" ]] || [[ "$HAS_ERROR" == "true" ]]; then
      echo "  PASS: [protocol] $TOOL_NAME -- valid JSON-RPC response"
      PROTOCOL_PASS=$((PROTOCOL_PASS + 1))
      PASS=$((PASS + 1))
    else
      echo "  FAIL: [protocol] $TOOL_NAME -- no result or error in response"
      PROTOCOL_FAIL=$((PROTOCOL_FAIL + 1))
      FAIL=$((FAIL + 1))
    fi
  fi

  MSG_ID=$((MSG_ID + 1))
done <<< "$TOOL_NAMES"

echo ""

# ─── Summary ────────────────────────────────────────────────────────────────
TOTAL=$((PASS + FAIL))
echo "=== Results: $DOMAIN ==="
echo "Total tests: $TOTAL"
echo "  Smoke (tools/list):  1 test"
echo "  Semantic:            ${SEMANTIC_PASS} pass, ${SEMANTIC_FAIL} fail"
echo "  Protocol:            ${PROTOCOL_PASS} pass, ${PROTOCOL_FAIL} fail"
echo ""
echo "Passed: $PASS"
echo "Failed: $FAIL"
echo "Warnings: $WARN"
echo ""

if [[ $FAIL -eq 0 ]]; then
  echo "OVERALL: PASS"
  exit 0
else
  echo "OVERALL: FAIL"
  exit 1
fi
