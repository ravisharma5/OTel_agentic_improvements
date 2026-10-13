#!/usr/bin/env bash
# deploy-build.sh -- Build the two-stage NextGCore image on a fresh cluster.
#
# Prerequisite: otel25-backends namespace exists (namespace.yaml-equivalent
# applied first, same as the rest of backends/openshift/).
#
# Usage: bash deploy-build.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="otel25-backends"

echo "[1/4] Applying BuildConfigs + ImageStreams..."
oc apply -f "${SCRIPT_DIR}/buildconfig-nextgcore.yaml"

echo ""
echo "[2/4] Cloning nextgcore + nextgsim into the sibling-directory layout"
echo "       docker/rust/Dockerfile.builder expects (it builds both together)..."
BUILD_CTX="$(mktemp -d)"
trap 'rm -rf "$BUILD_CTX"' EXIT
git clone --depth 1 https://github.com/NextgCoreLab/nextgcore.git "${BUILD_CTX}/nextgcore"
git clone --depth 1 https://github.com/NextgCoreLab/nextgsim.git "${BUILD_CTX}/nextgsim"

echo ""
echo "[3/4] Building nextgcore-builder (compiles all NF + nextgsim binaries,"
echo "       approximately 18 minutes)..."
oc start-build nextgcore-builder -n "$NAMESPACE" --from-dir="$BUILD_CTX" --follow

echo ""
echo "[4/4] Building nextgcore-runtime (combines compiled binaries with runtime deps,"
echo "       ~1 minute). This is a single-file binary build -- the Docker strategy"
echo "       with no file name treats a single --from-file upload as the Dockerfile."
oc start-build nextgcore-runtime -n "$NAMESPACE" --from-file="${SCRIPT_DIR}/Dockerfile.runtime" --follow

echo ""
echo "=== Done ==="
echo "Verify: oc get imagestreamtag nextgcore-runtime:latest -n ${NAMESPACE}"
echo "Next: apply deployment-nextgcore.yaml, configmap-nextgcore.yaml, scc-nextgcore-upf.yaml,"
echo "service-nwdaf.yaml (same directory)."
