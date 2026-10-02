#!/usr/bin/env bash
# check-nwdaf.sh -- NWDAF analytics endpoint smoke test (BACK-02)
#
# Tests the NWDAF AnalyticsInfo endpoint with analytics-specific field assertions
# per TS 29.520 spec. Uses one-shot analytics queries, not subscriptions
# (RESEARCH.md Pitfall 2: subscriptions are memory-only, lost on restart).
#
# Usage: NWDAF_BASE_URL=http://localhost:8080 ./check-nwdaf.sh
#        Or derive from ConfigMap:
#        export NWDAF_BASE_URL=$(oc get configmap backend-routing -n otel25-backends -o jsonpath='{.data.NWDAF_BASE_URL}')
#        ./check-nwdaf.sh
#
# IMPORTANT: The default URL assumes NextGCore (port 8080). When using Prism
# fallback (Path B per D-10), the port is 4010. Always set NWDAF_BASE_URL
# from the ConfigMap to get the correct port.

set -euo pipefail

NWDAF_URL="${NWDAF_BASE_URL:-http://nextgcore-nwdaf.otel25-backends.svc.cluster.local:8080}"

echo "=== NWDAF Analytics Smoke Test ==="
echo "Target: $NWDAF_URL"
echo ""

# Test 1: AnalyticsInfo endpoint with LOAD_LEVEL_INFORMATION event
ENDPOINT="${NWDAF_URL}/nnwdaf-analyticsinfo/v1/analytics?event-id=LOAD_LEVEL_INFORMATION"
echo "Test 1: GET $ENDPOINT"

RESPONSE=$(curl -s -w "\n%{http_code}" "$ENDPOINT" \
  -H "Accept: application/json" \
  --max-time 15 2>/dev/null || echo -e "\n000")
HTTP_CODE=$(echo "$RESPONSE" | tail -1)
BODY=$(echo "$RESPONSE" | sed '$d')

# Level 1: HTTP response check (hard gate)
if [[ "$HTTP_CODE" =~ ^2 ]]; then
  echo "  PASS: NWDAF responded with HTTP $HTTP_CODE"
else
  echo "  FAIL: NWDAF returned HTTP $HTTP_CODE"
  echo "  Note: If this is a new deployment, NWDAF may need time to initialize."
  echo "  Note: If NWDAF is consistently failing, consider fallback to Prism mock per D-10."
  exit 1
fi

# Level 2: Valid JSON check (hard gate)
if echo "$BODY" | jq . >/dev/null 2>&1; then
  echo "  PASS: response is valid JSON"
else
  echo "  FAIL: response is not valid JSON"
  echo "  Body: $BODY"
  exit 1
fi

# Level 3: Analytics-specific field assertions (soft gate -- warning only)
# Per TS 29.520 AnalyticsData schema, look for analytics-identifying fields:
#   - sliceLoadLevelInfos (array of SliceLoadLevelInformation)
#   - nsiLoadLevelInfos (array of NsiLoadLevelInfo)
#   - nfLoadLevelInfos (array of NfLoadLevelInformation)
#   - nwPerfs (array of NetworkPerfInfo)
#   - svcExps (array of ServiceExperienceInfo)
#   - expiry (DateTime)
#   - timeStampGen (DateTime)
ANALYTICS_FIELDS_FOUND=0
ANALYTICS_FIELDS_CHECKED=0

echo ""
echo "  Analytics field assertions (TS 29.520 AnalyticsData schema):"

# Check for load level info fields
for field in sliceLoadLevelInfos nsiLoadLevelInfos nfLoadLevelInfos; do
  ((ANALYTICS_FIELDS_CHECKED++))
  if echo "$BODY" | jq -e ".$field // empty" >/dev/null 2>&1; then
    echo "    FOUND: $field"
    ((ANALYTICS_FIELDS_FOUND++))
  fi
done

# Check for performance/experience fields
for field in nwPerfs svcExps; do
  ((ANALYTICS_FIELDS_CHECKED++))
  if echo "$BODY" | jq -e ".$field // empty" >/dev/null 2>&1; then
    echo "    FOUND: $field"
    ((ANALYTICS_FIELDS_FOUND++))
  fi
done

# Check for metadata fields
for field in expiry timeStampGen; do
  ((ANALYTICS_FIELDS_CHECKED++))
  if echo "$BODY" | jq -e ".$field // empty" >/dev/null 2>&1; then
    echo "    FOUND: $field"
    ((ANALYTICS_FIELDS_FOUND++))
  fi
done

echo ""
if [[ $ANALYTICS_FIELDS_FOUND -gt 0 ]]; then
  echo "  FIELD CHECK: $ANALYTICS_FIELDS_FOUND/$ANALYTICS_FIELDS_CHECKED analytics fields found"
  echo "  Confidence: HIGH -- response contains TS 29.520 analytics data"
else
  echo "  FIELD WARNING: 0/$ANALYTICS_FIELDS_CHECKED analytics fields found"
  echo "  The response is valid JSON but may not contain expected analytics structure."
  echo "  This can happen with Prism dynamic mode on complex 3GPP schemas."
  echo "  Review response body for manual inspection:"
  echo "$BODY" | jq . 2>/dev/null | head -20
fi

echo ""
echo "=== NWDAF Smoke Test Complete ==="
echo "HTTP: PASS | JSON: PASS | Fields: ${ANALYTICS_FIELDS_FOUND}/${ANALYTICS_FIELDS_CHECKED}"

# Exit success -- field checks are informational, not hard gates
exit 0
