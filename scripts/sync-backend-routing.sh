#!/usr/bin/env bash
# sync-backend-routing.sh -- Sync backend-routing ConfigMap from otel25-backends to otel25-mcp
#
# Purpose:
#   The canonical backend-routing ConfigMap lives in otel25-backends (D-17 single
#   source of truth). A copy exists in otel25-mcp because Kubernetes ConfigMaps
#   are namespace-scoped. This script reads the canonical copy and patches the
#   otel25-mcp copy to match, preventing silent backend routing drift.
#
# Usage:
#   scripts/sync-backend-routing.sh
#
# Prerequisites:
#   - oc CLI authenticated against the correct OpenShift cluster
#   - Read access to otel25-backends namespace
#   - Write access to otel25-mcp namespace
#   - jq installed
#
# Requires: bash 4+, oc, jq

set -euo pipefail

# --- Configuration ---
SOURCE_NS="otel25-backends"
TARGET_NS="otel25-mcp"
CONFIGMAP_NAME="backend-routing"

PASS=0
FAIL=0

# --- Preflight checks ---
echo "=== sync-backend-routing: ${SOURCE_NS} -> ${TARGET_NS} ==="
echo ""

# Check oc is available and authenticated
if ! command -v oc &>/dev/null; then
    echo "ERROR: oc CLI not found in PATH"
    exit 1
fi

if ! oc whoami &>/dev/null; then
    echo "ERROR: Not authenticated to OpenShift (run 'oc login' first)"
    exit 1
fi

echo "Authenticated as: $(oc whoami)"
echo ""

# Check jq is available
if ! command -v jq &>/dev/null; then
    echo "ERROR: jq not found in PATH (required for JSON processing)"
    exit 1
fi

# --- Step 1: Read canonical ConfigMap from source namespace ---
echo "--- Step 1: Reading canonical ConfigMap from ${SOURCE_NS} ---"

CANONICAL_JSON=$(oc get configmap "${CONFIGMAP_NAME}" -n "${SOURCE_NS}" -o json 2>/dev/null)
if [ -z "${CANONICAL_JSON}" ]; then
    echo "FAIL: Could not read ConfigMap '${CONFIGMAP_NAME}' from namespace '${SOURCE_NS}'"
    FAIL=$((FAIL + 1))
    echo ""
    echo "=== Results: sync ==="
    echo "Passed: ${PASS}"
    echo "Failed: ${FAIL}"
    echo ""
    echo "OVERALL: FAIL"
    exit 1
fi

echo "OK: Read canonical ConfigMap from ${SOURCE_NS}"
PASS=$((PASS + 1))

# --- Step 2: Extract .data section ---
echo ""
echo "--- Step 2: Extracting data keys ---"

DATA_JSON=$(echo "${CANONICAL_JSON}" | jq '.data')
if [ -z "${DATA_JSON}" ] || [ "${DATA_JSON}" = "null" ]; then
    echo "FAIL: ConfigMap '${CONFIGMAP_NAME}' in ${SOURCE_NS} has no data section"
    FAIL=$((FAIL + 1))
    echo ""
    echo "=== Results: sync ==="
    echo "Passed: ${PASS}"
    echo "Failed: ${FAIL}"
    echo ""
    echo "OVERALL: FAIL"
    exit 1
fi

SOURCE_KEY_COUNT=$(echo "${DATA_JSON}" | jq 'keys | length')
echo "OK: Extracted ${SOURCE_KEY_COUNT} keys from ${SOURCE_NS}"
PASS=$((PASS + 1))

# --- Step 3: Patch target namespace ConfigMap ---
echo ""
echo "--- Step 3: Patching ConfigMap in ${TARGET_NS} ---"

PATCH_PAYLOAD=$(jq -n --argjson data "${DATA_JSON}" '{"data": $data}')

if ! oc patch configmap "${CONFIGMAP_NAME}" -n "${TARGET_NS}" --type merge -p "${PATCH_PAYLOAD}" 2>/dev/null; then
    echo "FAIL: Could not patch ConfigMap '${CONFIGMAP_NAME}' in namespace '${TARGET_NS}'"
    echo "      Does the ConfigMap exist in ${TARGET_NS}? Create it first if not:"
    echo "      oc create configmap ${CONFIGMAP_NAME} -n ${TARGET_NS}"
    FAIL=$((FAIL + 1))
    echo ""
    echo "=== Results: sync ==="
    echo "Passed: ${PASS}"
    echo "Failed: ${FAIL}"
    echo ""
    echo "OVERALL: FAIL"
    exit 1
fi

echo "OK: Patched ConfigMap in ${TARGET_NS}"
PASS=$((PASS + 1))

# --- Step 4: Verify the patch ---
echo ""
echo "--- Step 4: Verifying sync ---"

TARGET_JSON=$(oc get configmap "${CONFIGMAP_NAME}" -n "${TARGET_NS}" -o json 2>/dev/null)
if [ -z "${TARGET_JSON}" ]; then
    echo "FAIL: Could not read ConfigMap from ${TARGET_NS} for verification"
    FAIL=$((FAIL + 1))
else
    TARGET_KEY_COUNT=$(echo "${TARGET_JSON}" | jq '.data | keys | length')
    if [ "${TARGET_KEY_COUNT}" -ge "${SOURCE_KEY_COUNT}" ]; then
        echo "OK: ${TARGET_NS} ConfigMap has ${TARGET_KEY_COUNT} keys (source has ${SOURCE_KEY_COUNT})"
        PASS=$((PASS + 1))
    else
        echo "FAIL: Key count mismatch -- ${TARGET_NS} has ${TARGET_KEY_COUNT}, expected at least ${SOURCE_KEY_COUNT}"
        FAIL=$((FAIL + 1))
    fi
fi

# --- Summary ---
echo ""
TOTAL=$((PASS + FAIL))
echo "=== Results: sync ==="
echo "Passed: ${PASS}"
echo "Failed: ${FAIL}"
echo ""
if [ "${FAIL}" -eq 0 ] && [ "${PASS}" -gt 0 ]; then
    echo "OVERALL: PASS -- ${SOURCE_NS}/${CONFIGMAP_NAME} synced to ${TARGET_NS}/${CONFIGMAP_NAME}"
    exit 0
else
    echo "OVERALL: FAIL"
    exit 1
fi
