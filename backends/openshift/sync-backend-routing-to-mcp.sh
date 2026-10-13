#!/usr/bin/env bash
# sync-backend-routing-to-mcp.sh -- Copy the backend-routing ConfigMap from
# otel25-backends into otel25-mcp.
#
# Kubernetes ConfigMap volumes are namespace-scoped: the 8 domain MCP servers
# in otel25-mcp mount their own copy, not the one in otel25-backends. The two
# were never kept in sync by anything automated (03-xx phase docs flagged this
# as a known operational gap, confirmed again live on sandbox4001 2026-10-13 --
# the otel25-mcp copy didn't exist on a fresh cluster until this ran).
#
# Run this after applying backends/openshift/configmap-backend-routing.yaml,
# and again any time that ConfigMap's data changes (e.g. switching a backend
# from Prism to a live service).
#
# Usage: bash sync-backend-routing-to-mcp.sh

set -euo pipefail

oc get cm backend-routing -n otel25-backends -o json | python3 -c "
import json, sys
d = json.load(sys.stdin)
d['metadata'] = {
    'name': d['metadata']['name'],
    'namespace': 'otel25-mcp',
    'annotations': {
        'otel25.io/copied-from': 'otel25-backends/backend-routing -- keep both in sync when backend URLs change (see this script)',
    },
}
print(json.dumps(d))
" | oc apply -f -
