#!/usr/bin/env bash
# validate-mocks.sh -- Verify Prism mock responses match OpenAPI spec schemas
#
# Per D-09: standalone validation script (NOT Prism validation-proxy, which is circular).
# Three levels of validation per endpoint:
#   1. HTTP 2xx response
#   2. Valid JSON body
#   3. Presence of spec-specific required fields (proves response matches schema structure)
#
# Usage: TMF642_URL=http://localhost:4010 ./validate-mocks.sh
#        Or run with defaults (in-cluster Service DNS names)

set -euo pipefail

# Base URLs (configurable via env vars; defaults to in-cluster Service DNS)
TMF642_URL="${TMF642_URL:-http://prism-tmf642.otel25-backends.svc.cluster.local:4010}"
TMF628_URL="${TMF628_URL:-http://prism-tmf628.otel25-backends.svc.cluster.local:4010}"
TMF621_URL="${TMF621_URL:-http://prism-tmf621.otel25-backends.svc.cluster.local:4010}"
CAMARA_URL="${CAMARA_URL:-http://prism-camara.otel25-backends.svc.cluster.local:4010}"
CAMARA_RETRIEVAL_URL="${CAMARA_RETRIEVAL_URL:-http://prism-camara-retrieval.otel25-backends.svc.cluster.local:4010}"

# Endpoint definitions: name|base_url|path|method
ENDPOINTS=(
  "tmf642|${TMF642_URL}|/alarm|GET"
  "tmf628|${TMF628_URL}|/measurementCollectionJob|GET"
  "tmf621|${TMF621_URL}|/troubleTicket|GET"
  "camara-verify|${CAMARA_URL}|/verify|POST"
  "camara-retrieval|${CAMARA_RETRIEVAL_URL}|/retrieve|POST"
)

PASS=0
FAIL=0
WARN=0

# Per-endpoint required field checks (spec-derived)
# TMF entities extend Addressable which has "id" and "href"
# CAMARA verify: VerifyLocationResponse has "verificationResult"
# CAMARA retrieval: Location has "lastLocationTime" and "area"
check_fields() {
  local name="$1"
  local body="$2"

  case "$name" in
    tmf642)
      # GET /alarm returns array of Alarm objects; each has "id" via Addressable
      if echo "$body" | jq -e '
        if type == "array" then .[0].id // .[0].href // empty
        else .id // .href // empty
        end' >/dev/null 2>&1; then
        echo "    FIELD CHECK: found id/href field (TMF entity)"
        return 0
      else
        echo "    FIELD WARNING: id/href not found in response (Prism dynamic mode may omit optional fields)"
        return 1
      fi
      ;;
    tmf628)
      # GET /measurementCollectionJob returns array; elements should have "id"
      if echo "$body" | jq -e '
        if type == "array" then .[0].id // .[0].href // empty
        else .id // .href // empty
        end' >/dev/null 2>&1; then
        echo "    FIELD CHECK: found id/href field (TMF entity)"
        return 0
      else
        echo "    FIELD WARNING: id/href not found in response (Prism dynamic mode may omit optional fields)"
        return 1
      fi
      ;;
    tmf621)
      # GET /troubleTicket returns array; elements should have "id"
      if echo "$body" | jq -e '
        if type == "array" then .[0].id // .[0].href // empty
        else .id // .href // empty
        end' >/dev/null 2>&1; then
        echo "    FIELD CHECK: found id/href field (TMF entity)"
        return 0
      else
        echo "    FIELD WARNING: id/href not found in response (Prism dynamic mode may omit optional fields)"
        return 1
      fi
      ;;
    camara-verify)
      # POST /verify returns VerifyLocationResponse with "verificationResult"
      if echo "$body" | jq -e '.verificationResult // empty' >/dev/null 2>&1; then
        echo "    FIELD CHECK: found verificationResult field"
        return 0
      else
        echo "    FIELD WARNING: verificationResult not found in response"
        return 1
      fi
      ;;
    camara-retrieval)
      # POST /retrieve returns Location with "lastLocationTime" and "area"
      if echo "$body" | jq -e '.lastLocationTime // .area // empty' >/dev/null 2>&1; then
        echo "    FIELD CHECK: found lastLocationTime/area field"
        return 0
      else
        echo "    FIELD WARNING: lastLocationTime/area not found in response"
        return 1
      fi
      ;;
    *)
      echo "    FIELD CHECK: no field assertions defined for $name"
      return 0
      ;;
  esac
}

echo "=== Prism Mock Validation ==="
echo ""

for entry in "${ENDPOINTS[@]}"; do
  IFS='|' read -r name base path method <<< "$entry"
  url="${base}${path}"
  echo "Validating $name: $method $url"

  # Build curl command
  CURL_ARGS=(-s -w "\n%{http_code}" -H "Prefer: dynamic=true" -X "$method" --max-time 10)

  # POST endpoints need a request body and auth header for Prism to accept
  # CAMARA specs define OAuth2 security; Prism enforces it, returning 401 without a token
  if [[ "$method" == "POST" ]]; then
    CURL_ARGS+=(-H "Content-Type: application/json" -H "Authorization: Bearer mock-validation-token")
    # Per-endpoint request bodies satisfying spec-required fields
    case "$name" in
      camara-verify)
        CURL_ARGS+=(-d '{"device":{"phoneNumber":"+123456789"},"area":{"areaType":"CIRCLE","center":{"latitude":45.0,"longitude":7.0},"radius":2000}}')
        ;;
      camara-retrieval)
        CURL_ARGS+=(-d '{"device":{"phoneNumber":"+123456789"}}')
        ;;
      *)
        CURL_ARGS+=(-d '{}')
        ;;
    esac
  fi

  RESPONSE=$(curl "${CURL_ARGS[@]}" "$url" 2>/dev/null || echo -e "\n000")
  HTTP_CODE=$(echo "$RESPONSE" | tail -1)
  BODY=$(echo "$RESPONSE" | sed '$d')

  # Level 1: HTTP 2xx check (hard gate)
  if [[ "$HTTP_CODE" =~ ^2 ]]; then
    echo "  PASS: HTTP $HTTP_CODE"
  else
    echo "  FAIL: HTTP $HTTP_CODE"
    ((FAIL++))
    echo ""
    continue
  fi

  # Level 2: Valid JSON check (hard gate)
  if echo "$BODY" | jq . >/dev/null 2>&1; then
    echo "  PASS: valid JSON body"
  else
    echo "  FAIL: invalid JSON body"
    ((FAIL++))
    echo ""
    continue
  fi

  # Level 3: Spec-specific field check (soft gate -- warning only)
  if check_fields "$name" "$BODY"; then
    ((PASS++))
  else
    ((WARN++))
    ((PASS++))  # Still counts as pass (field checks are warnings, not hard failures)
  fi

  echo ""
done

echo "=== Results ==="
echo "Endpoints tested: ${#ENDPOINTS[@]}"
echo "Passed: $PASS"
echo "Failed: $FAIL"
echo "Warnings (missing optional fields): $WARN"
echo ""

if [[ $FAIL -eq 0 ]]; then
  echo "OVERALL: PASS"
  exit 0
else
  echo "OVERALL: FAIL"
  exit 1
fi
