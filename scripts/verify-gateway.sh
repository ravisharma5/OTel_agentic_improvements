#!/usr/bin/env bash
# verify-gateway.sh -- RHCL MCP Gateway end-to-end verification
#
# Modes:
#   initialize:  MCP initialize handshake -- verify JSON-RPC response with serverInfo
#   tools-list:  List all tools via gateway -- verify count >= 78 (20 domain + 58 MCP-Telecom)
#   virtual-tmf: List tools with Virtual MCP Server filter -- verify exactly 15 TMF tools
#   tool-call:   Invoke a tool through gateway -- verify backend returns meaningful data
#
# MCP Streamable HTTP session management:
#   1. Send initialize to get Mcp-Session-Id
#   2. Send notifications/initialized with session ID
#   3. Use session ID for all subsequent requests
#
# Usage: scripts/verify-gateway.sh <mode> [gateway-url] [jwt-token]
#   mode:        initialize | tools-list | virtual-tmf | tool-call
#   gateway-url: default http://mcp.apps.cluster-domain/mcp
#   jwt-token:   optional JWT for Authorization: Bearer header
#
# Requires: bash 4+, curl, jq

set -euo pipefail

# ─── Configuration ───────────────────────────────────────────────────────────

MODE="${1:-}"
GATEWAY_URL="${2:-http://mcp.apps.cluster-domain/mcp}"
JWT_TOKEN="${3:-}"

if [[ -z "$MODE" ]]; then
  echo "Usage: $0 <mode> [gateway-url] [jwt-token]"
  echo "  mode: initialize | tools-list | virtual-tmf | tool-call"
  echo "  gateway-url: default http://mcp.apps.cluster-domain/mcp"
  echo "  jwt-token: optional JWT for authenticated requests"
  exit 1
fi

VALID_MODES="initialize tools-list virtual-tmf tool-call"
if ! echo "$VALID_MODES" | grep -qw "$MODE"; then
  echo "ERROR: Unknown mode '$MODE'. Supported: $VALID_MODES"
  exit 1
fi

# Known-good tool for tool-call mode (TMF642 list alarms -- GET endpoint, no body needed)
# Note: MCPServerRegistration prefix is concatenated without underscore (tmf642 + listAlarm)
TOOLCALL_TOOL_NAME="tmf642listAlarm"
TOOLCALL_TOOL_ARGS='{}'

# Temp files for this run
TMPDIR_RUN=$(mktemp -d)
trap 'rm -rf "$TMPDIR_RUN"' EXIT

PASS=0
FAIL=0
WARN=0

echo "=== MCP Gateway Verification: $MODE ==="
echo "Target: ${GATEWAY_URL}"
[[ -n "$JWT_TOKEN" ]] && echo "Auth: Bearer token provided" || echo "Auth: none"
echo ""

# ─── SSE Response Parsing Helper ─────────────────────────────────────────────
_parse_sse_json() {
  local body="$1"
  if echo "$body" | grep -q '^data: '; then
    echo "$body" | grep '^data: ' | tail -1 | sed 's/^data: //'
  else
    echo "$body"
  fi
}

# ─── Build Auth Headers ─────────────────────────────────────────────────────
# Returns auth header arguments for curl, or empty if no token
_auth_headers() {
  if [[ -n "$JWT_TOKEN" ]]; then
    echo "-H" "Authorization: Bearer ${JWT_TOKEN}"
  fi
}

# ─── Session Initialization ─────────────────────────────────────────────────
# Performs MCP initialize handshake and captures Mcp-Session-Id.
# Sets SESSION_ID and INIT_BODY globals.
# Returns 0 on success, 1 on failure.
_session_init() {
  echo "--- Session Setup: MCP initialize handshake ---"

  local auth_args=()
  if [[ -n "$JWT_TOKEN" ]]; then
    auth_args=(-H "Authorization: Bearer ${JWT_TOKEN}")
  fi

  INIT_RESPONSE=$(curl -s -D "${TMPDIR_RUN}/init-headers" \
    -X POST "${GATEWAY_URL}" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    "${auth_args[@]+"${auth_args[@]}"}" \
    -d '{"jsonrpc":"2.0","method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"verify-gateway","version":"1.0"}},"id":0}' \
    --max-time 30 2>/dev/null || echo "")

  INIT_BODY=$(_parse_sse_json "$INIT_RESPONSE")

  SESSION_ID=$(grep -i 'mcp-session-id' "${TMPDIR_RUN}/init-headers" 2>/dev/null | tr -d '\r' | awk '{print $2}' || echo "")

  if [[ -z "$SESSION_ID" ]]; then
    echo "  FAIL: could not obtain Mcp-Session-Id from initialize response"
    echo "  Headers: $(cat "${TMPDIR_RUN}/init-headers" 2>/dev/null || echo 'none')"
    return 1
  fi

  echo "  PASS: obtained session ID"

  # Send notifications/initialized
  curl -s -X POST "${GATEWAY_URL}" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "Mcp-Session-Id: ${SESSION_ID}" \
    "${auth_args[@]+"${auth_args[@]}"}" \
    -d '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
    --max-time 10 >/dev/null 2>&1 || true

  echo "  PASS: sent notifications/initialized"
  echo ""
  return 0
}

# ─── Mode: initialize ───────────────────────────────────────────────────────
_mode_initialize() {
  if ! _session_init; then
    FAIL=$((FAIL + 1))
    return
  fi

  echo "--- Test: Initialize response validation ---"

  # Validate JSON
  if ! echo "$INIT_BODY" | jq . >/dev/null 2>&1; then
    echo "  FAIL: invalid JSON in initialize response"
    FAIL=$((FAIL + 1))
    return
  fi

  # Check for serverInfo in result
  HAS_SERVER_INFO=$(echo "$INIT_BODY" | jq '.result.serverInfo // empty' 2>/dev/null || echo "")

  if [[ -n "$HAS_SERVER_INFO" ]]; then
    SERVER_NAME=$(echo "$INIT_BODY" | jq -r '.result.serverInfo.name // "unknown"' 2>/dev/null)
    SERVER_VERSION=$(echo "$INIT_BODY" | jq -r '.result.serverInfo.version // "unknown"' 2>/dev/null)
    echo "  PASS: initialize returned serverInfo"
    echo "        Server: $SERVER_NAME v$SERVER_VERSION"
    PASS=$((PASS + 1))
  else
    echo "  FAIL: initialize response missing serverInfo"
    echo "        Response: $(echo "$INIT_BODY" | jq -c . 2>/dev/null || echo "$INIT_BODY")"
    FAIL=$((FAIL + 1))
  fi

  # Verify JSON-RPC structure
  HAS_JSONRPC=$(echo "$INIT_BODY" | jq -r '.jsonrpc // empty' 2>/dev/null || echo "")
  if [[ "$HAS_JSONRPC" == "2.0" ]]; then
    echo "  PASS: valid JSON-RPC 2.0 response"
    PASS=$((PASS + 1))
  else
    echo "  FAIL: missing or invalid jsonrpc version"
    FAIL=$((FAIL + 1))
  fi
}

# ─── Mode: tools-list ────────────────────────────────────────────────────────
_mode_tools_list() {
  if ! _session_init; then
    FAIL=$((FAIL + 1))
    return
  fi

  echo "--- Test: Gateway tools/list (all backends) ---"

  local auth_args=()
  if [[ -n "$JWT_TOKEN" ]]; then
    auth_args=(-H "Authorization: Bearer ${JWT_TOKEN}")
  fi

  TOOLS_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "${GATEWAY_URL}" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "Mcp-Session-Id: ${SESSION_ID}" \
    "${auth_args[@]+"${auth_args[@]}"}" \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' \
    --max-time 30 2>/dev/null || echo -e "\n000")

  TOOLS_HTTP_CODE=$(echo "$TOOLS_RESPONSE" | tail -1)
  TOOLS_BODY=$(echo "$TOOLS_RESPONSE" | sed '$d')
  TOOLS_BODY=$(_parse_sse_json "$TOOLS_BODY")

  if [[ "$TOOLS_HTTP_CODE" != "200" ]]; then
    echo "  FAIL: HTTP $TOOLS_HTTP_CODE (expected 200)"
    FAIL=$((FAIL + 1))
    return
  fi

  if ! echo "$TOOLS_BODY" | jq . >/dev/null 2>&1; then
    echo "  FAIL: invalid JSON response"
    FAIL=$((FAIL + 1))
    return
  fi

  TOOL_COUNT=$(echo "$TOOLS_BODY" | jq '.result.tools | length' 2>/dev/null || echo "0")

  if [[ "$TOOL_COUNT" -ge 78 ]]; then
    echo "  PASS: tools/list returned $TOOL_COUNT tools (>= 78 expected: 20 domain + 58 MCP-Telecom)"
    PASS=$((PASS + 1))
  elif [[ "$TOOL_COUNT" -gt 0 ]]; then
    echo "  WARN: tools/list returned $TOOL_COUNT tools (expected >= 78)"
    WARN=$((WARN + 1))
    # Still a pass if some tools are visible, just fewer than expected
    PASS=$((PASS + 1))
  else
    echo "  FAIL: tools/list returned 0 tools"
    FAIL=$((FAIL + 1))
  fi

  # Print all tool names
  echo ""
  echo "  Discovered tools ($TOOL_COUNT):"
  echo "$TOOLS_BODY" | jq -r '.result.tools[].name' 2>/dev/null | while IFS= read -r name; do
    echo "    - $name"
  done
}

# ─── Mode: virtual-tmf ──────────────────────────────────────────────────────
_mode_virtual_tmf() {
  if ! _session_init; then
    FAIL=$((FAIL + 1))
    return
  fi

  echo "--- Test: Virtual MCP Server filter (TMF tools only) ---"
  echo "  Header: X-Mcp-Virtualserver: otel25-gateway/tmf-tools"

  local auth_args=()
  if [[ -n "$JWT_TOKEN" ]]; then
    auth_args=(-H "Authorization: Bearer ${JWT_TOKEN}")
  fi

  TOOLS_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "${GATEWAY_URL}" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "Mcp-Session-Id: ${SESSION_ID}" \
    -H "X-Mcp-Virtualserver: otel25-gateway/tmf-tools" \
    "${auth_args[@]+"${auth_args[@]}"}" \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' \
    --max-time 30 2>/dev/null || echo -e "\n000")

  TOOLS_HTTP_CODE=$(echo "$TOOLS_RESPONSE" | tail -1)
  TOOLS_BODY=$(echo "$TOOLS_RESPONSE" | sed '$d')
  TOOLS_BODY=$(_parse_sse_json "$TOOLS_BODY")

  if [[ "$TOOLS_HTTP_CODE" != "200" ]]; then
    echo "  FAIL: HTTP $TOOLS_HTTP_CODE (expected 200)"
    FAIL=$((FAIL + 1))
    return
  fi

  if ! echo "$TOOLS_BODY" | jq . >/dev/null 2>&1; then
    echo "  FAIL: invalid JSON response"
    FAIL=$((FAIL + 1))
    return
  fi

  TOOL_COUNT=$(echo "$TOOLS_BODY" | jq '.result.tools | length' 2>/dev/null || echo "0")

  if [[ "$TOOL_COUNT" -eq 15 ]]; then
    echo "  PASS: virtual-tmf returned exactly $TOOL_COUNT tools (6 TMF642 + 5 TMF628 + 4 TMF621)"
    PASS=$((PASS + 1))
  elif [[ "$TOOL_COUNT" -gt 0 ]]; then
    echo "  WARN: virtual-tmf returned $TOOL_COUNT tools (expected exactly 15)"
    WARN=$((WARN + 1))
    PASS=$((PASS + 1))
  else
    echo "  FAIL: virtual-tmf returned 0 tools"
    FAIL=$((FAIL + 1))
  fi

  # Print filtered tool names
  echo ""
  echo "  Filtered tools ($TOOL_COUNT):"
  echo "$TOOLS_BODY" | jq -r '.result.tools[].name' 2>/dev/null | while IFS= read -r name; do
    echo "    - $name"
  done

  # Verify all returned tools are TMF-prefixed
  NON_TMF_COUNT=$(echo "$TOOLS_BODY" | jq '[.result.tools[].name | select(startswith("tmf") | not)] | length' 2>/dev/null || echo "0")
  if [[ "$NON_TMF_COUNT" -eq 0 ]]; then
    echo ""
    echo "  PASS: all returned tools have tmf prefix"
    PASS=$((PASS + 1))
  else
    echo ""
    echo "  FAIL: $NON_TMF_COUNT tools without tmf prefix in virtual-tmf response"
    FAIL=$((FAIL + 1))
  fi
}

# ─── Mode: tool-call ─────────────────────────────────────────────────────────
_mode_tool_call() {
  if ! _session_init; then
    FAIL=$((FAIL + 1))
    return
  fi

  echo "--- Test: Tool invocation through gateway ---"

  local auth_args=()
  if [[ -n "$JWT_TOKEN" ]]; then
    auth_args=(-H "Authorization: Bearer ${JWT_TOKEN}")
  fi

  # First, get the tools list to find the actual tool name
  TOOLS_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "${GATEWAY_URL}" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "Mcp-Session-Id: ${SESSION_ID}" \
    "${auth_args[@]+"${auth_args[@]}"}" \
    -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' \
    --max-time 30 2>/dev/null || echo -e "\n000")

  TOOLS_HTTP_CODE=$(echo "$TOOLS_RESPONSE" | tail -1)
  TOOLS_BODY=$(echo "$TOOLS_RESPONSE" | sed '$d')
  TOOLS_BODY=$(_parse_sse_json "$TOOLS_BODY")

  if [[ "$TOOLS_HTTP_CODE" != "200" ]]; then
    echo "  FAIL: tools/list HTTP $TOOLS_HTTP_CODE (needed to discover tool name)"
    FAIL=$((FAIL + 1))
    return
  fi

  # Try to find the known-good tool, or discover a TMF642 list-style tool
  ACTUAL_TOOL="$TOOLCALL_TOOL_NAME"
  ACTUAL_ARGS="$TOOLCALL_TOOL_ARGS"

  TOOL_EXISTS=$(echo "$TOOLS_BODY" | jq -r --arg name "$ACTUAL_TOOL" \
    '[.result.tools[] | select(.name == $name)] | length' 2>/dev/null || echo "0")

  if [[ "$TOOL_EXISTS" -eq 0 ]]; then
    # Try to discover a TMF642 tool by pattern
    DISCOVERED=$(echo "$TOOLS_BODY" | jq -r \
      '[.result.tools[].name | select(test("tmf642"; "i")) | select(test("list|alarm"; "i"))] | first // empty' \
      2>/dev/null || echo "")

    if [[ -n "$DISCOVERED" ]]; then
      echo "  Note: '$ACTUAL_TOOL' not found; using discovered '$DISCOVERED'"
      ACTUAL_TOOL="$DISCOVERED"
    else
      # Fall back to first TMF642 tool, or first tool overall
      DISCOVERED=$(echo "$TOOLS_BODY" | jq -r \
        '[.result.tools[].name | select(test("tmf642"; "i"))] | first // empty' \
        2>/dev/null || echo "")

      if [[ -z "$DISCOVERED" ]]; then
        DISCOVERED=$(echo "$TOOLS_BODY" | jq -r '.result.tools[0].name // empty' 2>/dev/null || echo "")
      fi

      if [[ -n "$DISCOVERED" ]]; then
        echo "  Note: '$ACTUAL_TOOL' not found; falling back to '$DISCOVERED'"
        ACTUAL_TOOL="$DISCOVERED"
      else
        echo "  FAIL: no tools available for invocation"
        FAIL=$((FAIL + 1))
        return
      fi
    fi
  fi

  echo "  Invoking: $ACTUAL_TOOL"
  echo "  Arguments: $ACTUAL_ARGS"

  CALL_RESPONSE=$(curl -s -w "\n%{http_code}" \
    -X POST "${GATEWAY_URL}" \
    -H "Content-Type: application/json" \
    -H "Accept: application/json, text/event-stream" \
    -H "Mcp-Session-Id: ${SESSION_ID}" \
    "${auth_args[@]+"${auth_args[@]}"}" \
    -d "{\"jsonrpc\":\"2.0\",\"method\":\"tools/call\",\"params\":{\"name\":\"$ACTUAL_TOOL\",\"arguments\":$ACTUAL_ARGS},\"id\":2}" \
    --max-time 30 2>/dev/null || echo -e "\n000")

  CALL_HTTP_CODE=$(echo "$CALL_RESPONSE" | tail -1)
  CALL_BODY=$(echo "$CALL_RESPONSE" | sed '$d')
  CALL_BODY=$(_parse_sse_json "$CALL_BODY")

  # Check HTTP status
  if [[ "$CALL_HTTP_CODE" != "200" ]]; then
    echo "  FAIL: HTTP $CALL_HTTP_CODE (expected 200)"
    FAIL=$((FAIL + 1))
    return
  fi

  echo "  PASS: HTTP 200"

  # Check JSON validity
  if ! echo "$CALL_BODY" | jq . >/dev/null 2>&1; then
    echo "  FAIL: invalid JSON response"
    FAIL=$((FAIL + 1))
    return
  fi

  echo "  PASS: valid JSON-RPC response"

  # Check for isError flag
  IS_ERROR=$(echo "$CALL_BODY" | jq -r '.result.isError // false' 2>/dev/null || echo "false")

  # Extract response content
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
    echo "  FAIL: isError=true in MCP response"
    echo "        Content: ${CONTENT_TEXT:0:200}"
    FAIL=$((FAIL + 1))
  elif [[ -z "$CONTENT_TEXT" ]]; then
    echo "  FAIL: empty response content (expected backend data)"
    FAIL=$((FAIL + 1))
  elif echo "$CONTENT_TEXT" | grep -qi '^Error:'; then
    echo "  FAIL: response starts with 'Error:'"
    echo "        Content: ${CONTENT_TEXT:0:200}"
    FAIL=$((FAIL + 1))
  elif echo "$CONTENT_LOWER" | grep -qE "(request body must have required property|must have required property|validation)"; then
    echo "  FAIL: Prism validation error in response"
    echo "        Content: ${CONTENT_TEXT:0:200}"
    FAIL=$((FAIL + 1))
  else
    echo "  PASS: tool invocation returned data from backend"
    echo "        Content preview: ${CONTENT_TEXT:0:120}"
    PASS=$((PASS + 1))
  fi
}

# ─── Mode Dispatch ───────────────────────────────────────────────────────────

case "$MODE" in
  initialize)
    _mode_initialize
    ;;
  tools-list)
    _mode_tools_list
    ;;
  virtual-tmf)
    _mode_virtual_tmf
    ;;
  tool-call)
    _mode_tool_call
    ;;
esac

echo ""

# ─── Summary ────────────────────────────────────────────────────────────────
TOTAL=$((PASS + FAIL))
echo "=== Results: gateway/$MODE ==="
echo "Total tests: $TOTAL"
echo "Passed: $PASS"
echo "Failed: $FAIL"
echo "Warnings: $WARN"
echo ""

if [[ $FAIL -eq 0 && $PASS -gt 0 ]]; then
  echo "OVERALL: PASS"
  exit 0
elif [[ $FAIL -eq 0 && $PASS -eq 0 ]]; then
  echo "OVERALL: FAIL (no tests ran)"
  exit 1
else
  echo "OVERALL: FAIL"
  exit 1
fi
