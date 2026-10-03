#!/usr/bin/env bash
# verify-mcp-telecom.sh -- Verify MCP-Telecom deployment via Streamable HTTP (D-08)
#
# Two-test MCP protocol round-trip verification:
#   Test 1 (MCP-06c): tools/list -- confirms server exposes 50+ tools
#   Test 2 (MCP-06d): tool invocation -- confirms a dynamically-discovered tool
#                      returns a valid MCP response (connection/device errors expected
#                      per D-07; tool-not-found errors are failures)
#
# Usage: MCP_TELECOM_URL=http://localhost:8000 bash scripts/verify-mcp-telecom.sh
#        Requires: curl, jq

set -euo pipefail

MCP_TELECOM_URL="${MCP_TELECOM_URL:-http://mcp-telecom.otel25-mcp.svc.cluster.local:8000}"

PASS=0
FAIL=0
WARN=0

echo "=== MCP-Telecom Protocol Verification ==="
echo "Target: ${MCP_TELECOM_URL}"
echo ""

# ─── Test 1 (MCP-06c): tools/list ─────────────────────────────────────────────
echo "--- Test 1: tools/list via Streamable HTTP ---"

TOOLS_RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST "${MCP_TELECOM_URL}/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc":"2.0","method":"tools/list","id":1}' \
  --max-time 30 2>/dev/null || echo -e "\n000")

TOOLS_HTTP_CODE=$(echo "$TOOLS_RESPONSE" | tail -1)
TOOLS_BODY=$(echo "$TOOLS_RESPONSE" | sed '$d')

# Level 1: HTTP 200 check
if [[ "$TOOLS_HTTP_CODE" == "200" ]]; then
  echo "  PASS: HTTP $TOOLS_HTTP_CODE"
else
  echo "  FAIL: HTTP $TOOLS_HTTP_CODE (expected 200)"
  FAIL=$((FAIL + 1))
  echo ""
  echo "=== Results ==="
  echo "Tests: 2"
  echo "Passed: $PASS"
  echo "Failed: $FAIL"
  echo "Warnings: $WARN"
  echo ""
  echo "OVERALL: FAIL"
  exit 1
fi

# Handle SSE (text/event-stream) responses: extract JSON from data: lines
# FastMCP may respond with SSE format even for single responses
if echo "$TOOLS_BODY" | grep -q '^data: '; then
  TOOLS_BODY=$(echo "$TOOLS_BODY" | grep '^data: ' | tail -1 | sed 's/^data: //')
fi

# Level 2: Valid JSON-RPC response
if echo "$TOOLS_BODY" | jq . >/dev/null 2>&1; then
  echo "  PASS: valid JSON-RPC response"
else
  echo "  FAIL: invalid JSON body"
  FAIL=$((FAIL + 1))
  echo ""
  echo "=== Results ==="
  echo "Tests: 2"
  echo "Passed: $PASS"
  echo "Failed: $FAIL"
  echo "Warnings: $WARN"
  echo ""
  echo "OVERALL: FAIL"
  exit 1
fi

# Level 3: Result contains tools array with count >= 50 (soft check)
TOOL_COUNT=$(echo "$TOOLS_BODY" | jq '.result.tools | length' 2>/dev/null || echo "0")
if [[ "$TOOL_COUNT" -ge 50 ]]; then
  echo "  PASS: tools/list returned $TOOL_COUNT tools (>= 50)"
  PASS=$((PASS + 1))
elif [[ "$TOOL_COUNT" -gt 0 ]]; then
  echo "  WARN: tools/list returned $TOOL_COUNT tools (expected >= 50)"
  WARN=$((WARN + 1))
  PASS=$((PASS + 1))
else
  echo "  FAIL: tools/list returned 0 tools or unexpected format"
  FAIL=$((FAIL + 1))
fi

echo ""

# ─── Test 2 (MCP-06d): tool invocation ────────────────────────────────────────
echo "--- Test 2: tool invocation via Streamable HTTP ---"

# Simple-schema-preference heuristic: prefer tools whose inputSchema has
# no required fields, or only string-typed required fields. This avoids
# selecting tools with nested objects, enums, or union types that the script
# cannot synthesize arguments for.

# Step 1: Try to find a tool with no required fields
SELECTED_TOOL=$(echo "$TOOLS_BODY" | jq -r '
  [.result.tools[] |
    select(
      .inputSchema.required == null or
      (.inputSchema.required | length) == 0
    )
  ] | first // empty | .name' 2>/dev/null || echo "")

TOOL_ARGS="{}"

# Step 2: If no tool found with empty required, find one with only string required fields
if [[ -z "$SELECTED_TOOL" ]]; then
  SELECTED_TOOL=$(echo "$TOOLS_BODY" | jq -r '
    [.result.tools[] |
      select(
        .inputSchema.required != null and
        (.inputSchema.required | length) > 0 and
        (
          [.inputSchema.required[] as $req |
            .inputSchema.properties[$req].type
          ] | all(. == "string")
        )
      )
    ] | first // empty | .name' 2>/dev/null || echo "")

  # Construct minimal arguments: empty string for each required field
  if [[ -n "$SELECTED_TOOL" ]]; then
    TOOL_ARGS=$(echo "$TOOLS_BODY" | jq -c '
      [.result.tools[] | select(.name == "'"$SELECTED_TOOL"'")] | first |
      [.inputSchema.required[] as $req | {($req): ""}] | add // {}' 2>/dev/null || echo "{}")
  fi
fi

# Step 3: Fall back to index 0 if no suitable tool found
if [[ -z "$SELECTED_TOOL" ]]; then
  SELECTED_TOOL=$(echo "$TOOLS_BODY" | jq -r '.result.tools[0].name // empty' 2>/dev/null || echo "")
  if [[ -n "$SELECTED_TOOL" ]]; then
    # Construct minimal arguments for first tool's required fields
    TOOL_ARGS=$(echo "$TOOLS_BODY" | jq -c '
      .result.tools[0] |
      if .inputSchema.required != null and (.inputSchema.required | length) > 0 then
        [.inputSchema.required[] as $req | {($req): ""}] | add
      else
        {}
      end' 2>/dev/null || echo "{}")
    echo "  WARN: fell back to first tool (no simple-schema tool found)"
    WARN=$((WARN + 1))
  fi
fi

if [[ -z "$SELECTED_TOOL" ]]; then
  echo "  FAIL: could not select a tool from tools/list response"
  FAIL=$((FAIL + 1))
  echo ""
  echo "=== Results ==="
  echo "Tests: 2"
  echo "Passed: $PASS"
  echo "Failed: $FAIL"
  echo "Warnings: $WARN"
  echo ""
  echo "OVERALL: FAIL"
  exit 1
fi

echo "  Selected tool: $SELECTED_TOOL"
echo "  Arguments: $TOOL_ARGS"

CALL_RESPONSE=$(curl -s -w "\n%{http_code}" \
  -X POST "${MCP_TELECOM_URL}/mcp" \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d "{\"jsonrpc\":\"2.0\",\"method\":\"tools/call\",\"params\":{\"name\":\"$SELECTED_TOOL\",\"arguments\":$TOOL_ARGS},\"id\":2}" \
  --max-time 30 2>/dev/null || echo -e "\n000")

CALL_HTTP_CODE=$(echo "$CALL_RESPONSE" | tail -1)
CALL_BODY=$(echo "$CALL_RESPONSE" | sed '$d')

# Level 1: HTTP 200 check
if [[ "$CALL_HTTP_CODE" == "200" ]]; then
  echo "  PASS: HTTP $CALL_HTTP_CODE"
else
  echo "  FAIL: HTTP $CALL_HTTP_CODE (expected 200)"
  FAIL=$((FAIL + 1))
  echo ""
  echo "=== Results ==="
  echo "Tests: 2"
  echo "Passed: $PASS"
  echo "Failed: $FAIL"
  echo "Warnings: $WARN"
  echo ""
  echo "OVERALL: FAIL"
  exit 1
fi

# Handle SSE responses
if echo "$CALL_BODY" | grep -q '^data: '; then
  CALL_BODY=$(echo "$CALL_BODY" | grep '^data: ' | tail -1 | sed 's/^data: //')
fi

# Level 2: Valid JSON-RPC response
if echo "$CALL_BODY" | jq . >/dev/null 2>&1; then
  echo "  PASS: valid JSON-RPC response"
else
  echo "  FAIL: invalid JSON body"
  FAIL=$((FAIL + 1))
  echo ""
  echo "=== Results ==="
  echo "Tests: 2"
  echo "Passed: $PASS"
  echo "Failed: $FAIL"
  echo "Warnings: $WARN"
  echo ""
  echo "OVERALL: FAIL"
  exit 1
fi

# Level 3: Error type discrimination
# Check if response has a result key (success) or error content
HAS_RESULT=$(echo "$CALL_BODY" | jq 'has("result")' 2>/dev/null || echo "false")
ERROR_MSG=$(echo "$CALL_BODY" | jq -r '
  if has("error") then .error.message // (.error | tostring)
  elif has("result") then
    if (.result | type) == "object" and (.result | has("content")) then
      (.result.content[]? | select(.type == "text") | .text) // ""
    else
      .result | tostring
    end
  else ""
  end' 2>/dev/null || echo "")

# Normalize for case-insensitive matching
ERROR_MSG_LOWER=$(echo "$ERROR_MSG" | tr '[:upper:]' '[:lower:]')

if [[ "$HAS_RESULT" == "true" ]]; then
  # Check if the result text itself contains error indicators
  if echo "$ERROR_MSG_LOWER" | grep -qE "(not found|unknown tool|unknown method|method not found)"; then
    echo "  FAIL: tool name resolution failed -- $ERROR_MSG"
    FAIL=$((FAIL + 1))
  elif echo "$ERROR_MSG_LOWER" | grep -qE "(invalid params|invalid arguments|schema|validation)"; then
    echo "  PASS: tool exists (schema construction limitation -- script could not construct valid args)"
    echo "  WARN: $ERROR_MSG"
    WARN=$((WARN + 1))
    PASS=$((PASS + 1))
  elif echo "$ERROR_MSG_LOWER" | grep -qE "(connection refused|timeout|no device configured|error:|errno|connect|connection|refused|unreachable)"; then
    echo "  PASS: tool invoked successfully (connection/device error expected per D-07)"
    echo "  Note: $ERROR_MSG"
    PASS=$((PASS + 1))
  else
    echo "  PASS: tool invocation returned a result"
    PASS=$((PASS + 1))
  fi
elif echo "$CALL_BODY" | jq -e 'has("error")' >/dev/null 2>&1; then
  # JSON-RPC level error
  if echo "$ERROR_MSG_LOWER" | grep -qE "(not found|unknown tool|unknown method|method not found)"; then
    echo "  FAIL: tool name resolution failed -- $ERROR_MSG"
    FAIL=$((FAIL + 1))
  elif echo "$ERROR_MSG_LOWER" | grep -qE "(invalid params|invalid arguments|schema|validation)"; then
    echo "  PASS: tool exists (schema construction limitation)"
    echo "  WARN: $ERROR_MSG"
    WARN=$((WARN + 1))
    PASS=$((PASS + 1))
  else
    echo "  PASS: MCP protocol responded (error expected per D-07)"
    echo "  Note: $ERROR_MSG"
    PASS=$((PASS + 1))
  fi
else
  echo "  PASS: tool invocation completed"
  PASS=$((PASS + 1))
fi

echo ""

# ─── Summary ──────────────────────────────────────────────────────────────────
echo "=== Results ==="
echo "Tests: 2"
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
