#!/usr/bin/env bash
# merge-virtualserver-config.sh -- Work around a real gap in the RHCL MCP Gateway
# operator (v0.7.1, Tech Preview, confirmed live on sandbox4001 2026-10-13, and
# previously on sandbox1330/3435 per 03-REVIEWS.md): the MCPVirtualServer
# controller writes its reconciled `virtualServers` config to a secret in a
# `mcp-system` namespace it expects to already exist (and which nothing else
# creates), while the actual gateway broker reads its config from a different
# secret, `otel25-gateway/mcp-gateway-config`. The two are never merged
# automatically -- every MCPVirtualServer stays permanently stuck reconciling
# with "namespaces \"mcp-system\" not found" until that namespace exists, and
# even once it does, the broker's own config secret needs the `virtualServers`
# section merged in by hand and the broker restarted to pick it up.
#
# Run this after applying mcpsr-*.yaml and mcpvs-*.yaml (gateway/openshift/),
# once `oc get mcpvirtualserver -n otel25-gateway` shows your virtual servers.
#
# Usage: bash merge-virtualserver-config.sh

set -euo pipefail

oc get namespace mcp-system >/dev/null 2>&1 || oc create namespace mcp-system

echo "Waiting for the controller to populate mcp-system's config secret..."
for i in $(seq 1 20); do
  if oc get secret mcp-gateway-config -n mcp-system >/dev/null 2>&1; then
    break
  fi
  sleep 3
done

VS_YAML=$(oc get secret mcp-gateway-config -n mcp-system -o jsonpath='{.data.config\.yaml}' | base64 -d)
BROKER_YAML=$(oc get secret mcp-gateway-config -n otel25-gateway -o jsonpath='{.data.config\.yaml}' | base64 -d)

MERGED_B64=$(python3 -c "
import yaml, base64

vs_doc = yaml.safe_load('''$VS_YAML''')
broker_doc = yaml.safe_load('''$BROKER_YAML''')
broker_doc['virtualServers'] = vs_doc['virtualServers']
merged = yaml.safe_dump(broker_doc, default_flow_style=False)
print(base64.b64encode(merged.encode()).decode())
")

oc patch secret mcp-gateway-config -n otel25-gateway --type=json \
  -p="[{\"op\":\"replace\",\"path\":\"/data/config.yaml\",\"value\":\"${MERGED_B64}\"}]"

echo "Restarting mcp-gateway broker to pick up the merged config..."
oc rollout restart deployment/mcp-gateway -n otel25-gateway
oc rollout status deployment/mcp-gateway -n otel25-gateway --timeout=120s

echo ""
echo "Done. Verify with a direct tools/list call against the gateway -- expect ~84 tools"
echo "(8 domain servers' tool counts, matching the known-healthy baseline from prior clusters)."
echo ""
echo "NOTE: if any MCPServerRegistration or MCPVirtualServer is re-reconciled later (added,"
echo "removed, or the operator restarts), re-run this script -- the merge does not persist"
echo "through a fresh reconcile of the broker's config secret."
