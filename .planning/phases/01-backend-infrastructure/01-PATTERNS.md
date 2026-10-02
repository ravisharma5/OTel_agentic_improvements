# Phase 1: Backend Infrastructure - Pattern Map

**Mapped:** 2026-09-27
**Revised:** 2026-10-02 (updated Prism manifest count to 5, CAMARA probe to tcpSocket, ConfigMap to 6 keys with mounted-file contract)
**Files analyzed:** 21 new files to create
**Analogs found:** 0 / 21 (greenfield repo -- no existing application code, Dockerfiles, manifests, or scripts)

## Greenfield Notice

This repository contains only markdown planning/research documents and a `.planning/config.json`. There are no existing Dockerfiles, Kubernetes/OpenShift manifests, shell scripts, or application code to serve as in-repo analogs. All pattern assignments below reference **RESEARCH.md code examples** as the canonical patterns to copy, since those were explicitly designed for this project's stack (Prism, OpenShift, NextGCore, ConfigMap routing).

## File Classification

| New File | Role | Data Flow | Closest Analog | Match Quality |
|----------|------|-----------|----------------|---------------|
| `backends/specs/tmf642_alarm_v5.0.1.oas.yaml` | config (vendored spec) | N/A (static asset) | No analog | N/A -- downloaded from upstream |
| `backends/specs/tmf628_performance_v4.0.0.swagger.json` | config (vendored spec) | N/A (static asset) | No analog | N/A -- downloaded from upstream |
| `backends/specs/tmf621_troubleticket_v5.0.1.oas.yaml` | config (vendored spec) | N/A (static asset) | No analog | N/A -- downloaded from upstream |
| `backends/specs/camara_location_verification.yaml` | config (vendored spec) | N/A (static asset) | No analog | N/A -- downloaded from upstream |
| `backends/specs/camara_location_retrieval.yaml` | config (vendored spec) | N/A (static asset) | No analog | N/A -- downloaded from upstream |
| `backends/specs/nwdaf_analyticsinfo_rel16.yaml` | config (vendored spec) | N/A (static asset) | No analog | N/A -- downloaded from upstream |
| `backends/specs/nwdaf_eventssubscription_rel16.yaml` | config (vendored spec) | N/A (static asset) | No analog | N/A -- downloaded from upstream |
| `backends/prism/Dockerfile` | config (container image) | N/A (build artifact) | No analog | N/A -- greenfield |
| `backends/nextgcore/docker-compose.local.yaml` | config (compose) | N/A (orchestration) | No analog | N/A -- greenfield |
| `backends/openshift/namespace.yaml` | config (k8s manifest) | N/A (declarative infra) | No analog | N/A -- greenfield |
| `backends/openshift/prism-tmf642.yaml` | config (k8s manifest) | request-response | No analog | N/A -- greenfield |
| `backends/openshift/prism-tmf628.yaml` | config (k8s manifest) | request-response | No analog | N/A -- greenfield |
| `backends/openshift/prism-tmf621.yaml` | config (k8s manifest) | request-response | No analog | N/A -- greenfield |
| `backends/openshift/prism-camara.yaml` | config (k8s manifest) | request-response | No analog | N/A -- greenfield |
| `backends/openshift/prism-camara-retrieval.yaml` | config (k8s manifest) | request-response | No analog | N/A -- greenfield |
| `backends/openshift/nextgcore/scc-nextgcore-upf.yaml` | config (security policy) | N/A (declarative infra) | No analog | N/A -- greenfield |
| `backends/openshift/nextgcore/deployment-nextgcore.yaml` | config (k8s manifest) | request-response | No analog | N/A -- greenfield |
| `backends/openshift/nextgcore/service-nwdaf.yaml` | config (k8s manifest) | request-response | No analog | N/A -- greenfield |
| `backends/openshift/configmap-backend-routing.yaml` | config (routing) | N/A (declarative infra) | No analog | N/A -- greenfield |
| `backends/scripts/validate-mocks.sh` | test (validation script) | request-response | No analog | N/A -- greenfield |
| `backends/scripts/verify-routing.sh` | test (integration script) | request-response | No analog | N/A -- greenfield |
| `backends/scripts/check-nwdaf.sh` | test (smoke test) | request-response | No analog | N/A -- greenfield |

## Pattern Assignments

Since no in-repo analogs exist, each pattern assignment below references the concrete code examples from `01-RESEARCH.md` that should be copied as the starting point for each file.

---

### `backends/specs/*` (vendored OpenAPI specs -- 7 files)

**Role:** Static configuration assets, downloaded from upstream and committed verbatim.

**No pattern needed.** These are downloaded files, not authored. The planner should use the download URLs from RESEARCH.md "OpenAPI Spec Vendoring Details" table:

| File | Source URL |
|------|-----------|
| `tmf642_alarm_v5.0.1.oas.yaml` | `https://raw.githubusercontent.com/tmforum-apis/TMF642_AlarmManagement/main/TMF642_Alarm_v5.0.1.oas.yaml` |
| `tmf628_performance_v4.0.0.swagger.json` | `https://raw.githubusercontent.com/tmforum-apis/TMF628_Performance/main/TMF628-Performance-v4.0.0.swagger.json` |
| `tmf621_troubleticket_v5.0.1.oas.yaml` | `https://raw.githubusercontent.com/tmforum-apis/TMF621_TroubleTicket/main/TMF621-Trouble_Ticket-v5.0.1.oas.yaml` |
| `camara_location_verification.yaml` | `https://raw.githubusercontent.com/camaraproject/DeviceLocation/r3.2/code/API_definitions/location-verification.yaml` |
| `camara_location_retrieval.yaml` | `https://raw.githubusercontent.com/camaraproject/DeviceLocation/r3.2/code/API_definitions/location-retrieval.yaml` |
| `nwdaf_analyticsinfo_rel16.yaml` | `https://raw.githubusercontent.com/jdegre/5GC_APIs/Rel-16/TS29520_Nnwdaf_AnalyticsInfo.yaml` |
| `nwdaf_eventssubscription_rel16.yaml` | `https://raw.githubusercontent.com/jdegre/5GC_APIs/Rel-16/TS29520_Nnwdaf_EventsSubscription.yaml` |

---

### `backends/prism/Dockerfile` (container image, build artifact)

**Source pattern:** RESEARCH.md "Pattern 1: One Prism Instance Per API Spec" -- Example Dockerfile

**Copy this Dockerfile pattern** (RESEARCH.md lines 217-229):
```dockerfile
FROM stoplight/prism:5

# Copy the vendored spec into the image
COPY specs/tmf642_alarm_v5.0.1.oas.yaml /specs/api.yaml

# Run in dynamic mode, bind to all interfaces, production mode
ENV NODE_ENV=production
ENTRYPOINT ["node", "dist/index.js"]
CMD ["mock", "-h", "0.0.0.0", "-p", "4010", "--dynamic", "/specs/api.yaml"]
```

**Key constraints from RESEARCH.md anti-patterns:**
- MUST bind to `0.0.0.0` (not localhost) -- otherwise unreachable from outside container
- MUST set `NODE_ENV=production` -- processing logs slow Prism significantly without it
- MUST use `--dynamic` flag -- generates varied responses from schema (D-08)
- One Dockerfile per API spec, or a parameterized Dockerfile with build args for the spec file path

**Prism version note (RESEARCH.md Pitfall 1):**
- Docker Hub `stoplight/prism:5` resolves to 5.15.10 (lags npm 5.16.0)
- For exact version pinning, build from `node:24-slim` + `npm install -g @stoplight/prism-cli@5.16.0`
- Functionally equivalent for mocking -- v5.16.0 changes were dependency bumps, not mocking features

---

### `backends/openshift/prism-tmf642.yaml` (k8s manifest, request-response)

**Applies to all 5 Prism Deployment+Service manifests:** `prism-tmf642.yaml`, `prism-tmf628.yaml`, `prism-tmf621.yaml`, `prism-camara.yaml`, `prism-camara-retrieval.yaml`

**Source pattern:** RESEARCH.md "Pattern 1" -- Example OpenShift Deployment + Service (RESEARCH.md lines 232-294)

**Deployment pattern:**
```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prism-tmf642
  namespace: otel25-backends
  labels:
    app: prism-tmf642
    api: tmf642
spec:
  replicas: 1
  selector:
    matchLabels:
      app: prism-tmf642
  template:
    metadata:
      labels:
        app: prism-tmf642
    spec:
      containers:
      - name: prism
        image: image-registry.openshift-image-registry.svc:5000/otel25-backends/prism-tmf642:latest
        ports:
        - containerPort: 4010
          protocol: TCP
        env:
        - name: NODE_ENV
          value: "production"
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 250m
            memory: 256Mi
        readinessProbe:
          httpGet:
            path: /alarm          # Must be a valid GET path from the spec
            port: 4010
          initialDelaySeconds: 5
          periodSeconds: 10
        livenessProbe:
          httpGet:
            path: /alarm
            port: 4010
          initialDelaySeconds: 10
          periodSeconds: 30
```

**Service pattern:**
```yaml
apiVersion: v1
kind: Service
metadata:
  name: prism-tmf642
  namespace: otel25-backends
spec:
  selector:
    app: prism-tmf642
  ports:
  - port: 4010
    targetPort: 4010
    protocol: TCP
  type: ClusterIP
```

**Per-API health check paths (RESEARCH.md Pitfall 4):**
Prism has no `/health` endpoint. Probe selection depends on whether the spec has a safe GET path:
- TMF642: `httpGet` on `/alarm`
- TMF628: `httpGet` on `/measurementCollectionJob` (verify this exists in Swagger 2.0 spec)
- TMF621: `httpGet` on `/troubleTicket`
- CAMARA (prism-camara and prism-camara-retrieval): `tcpSocket` on port 4010. Both CAMARA specs are POST-heavy with no safe GET endpoints; httpGet probes would receive HTTP 4xx/405 responses causing crash-looping. The tcpSocket probe confirms the Prism process is listening without requiring a valid HTTP request. (Decided in 01-03-PLAN.md revision.)

**Per-API variation:**
- Each manifest replaces `tmf642` with the API name (`tmf628`, `tmf621`, `camara`, `camara-retrieval`)
- Each uses its own image (`prism-tmf628:latest`, etc.)
- Health check path changes per spec (see above)
- TMF628 note (RESEARCH.md Pitfall 5): Swagger 2.0 JSON spec -- test locally first for circular $ref issues

---

### `backends/openshift/namespace.yaml` (k8s manifest, declarative infra)

**Standard OpenShift namespace resource. No complex pattern needed.**

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: otel25-backends
  labels:
    purpose: phase-1-backends
```

Or use `oc new-project otel25-backends` imperatively (RESEARCH.md "Cluster Login Setup").

---

### `backends/openshift/configmap-backend-routing.yaml` (routing config, declarative infra)

**Source pattern:** RESEARCH.md "Pattern 2: ConfigMap-Based Backend Routing" (RESEARCH.md lines 302-316)

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: backend-routing
  namespace: otel25-backends
data:
  TMF642_BASE_URL: "http://prism-tmf642.otel25-backends.svc.cluster.local:4010"
  TMF628_BASE_URL: "http://prism-tmf628.otel25-backends.svc.cluster.local:4010"
  TMF621_BASE_URL: "http://prism-tmf621.otel25-backends.svc.cluster.local:4010"
  CAMARA_BASE_URL: "http://prism-camara.otel25-backends.svc.cluster.local:4010"
  CAMARA_RETRIEVAL_BASE_URL: "http://prism-camara-retrieval.otel25-backends.svc.cluster.local:4010"
  NWDAF_BASE_URL: "http://nextgcore-nwdaf.otel25-backends.svc.cluster.local:8080"
```

**Key design constraints:**

- **(D-15, ARCHITECTURE.md Anti-Pattern 5):** Backend URLs must never be embedded in code. The same code must work against Prism and live backends by reading from ConfigMap.

- **(D-14):** 6 keys, one per API: TMF642, TMF628, TMF621, CAMARA (verification), CAMARA_RETRIEVAL, NWDAF.

- **Consumer contract -- mounted-file consumption ONLY for no-redeploy compliance (D-15, BACK-03):** Phase 2/3 MCP servers MUST consume this ConfigMap via volume mount (not envFrom/env). Only mounted-file consumption enables live switching without pod restart -- the kubelet updates mounted ConfigMap files within ~1 minute of an edit. Env-var consumption (envFrom or individual env entries) reads values at pod startup only; changing the ConfigMap would require a pod restart, violating BACK-03's "switch without redeploying services" criterion. The ConfigMap YAML should include a comment block documenting this contract. See 01-04-PLAN.md for full details.

- **NWDAF port varies by path:** Port 8080 for NextGCore Path A, port 4010 for Prism Path B. The ConfigMap value is the single source of truth; verification scripts (check-nwdaf.sh, verify-routing.sh) derive the NWDAF URL from the ConfigMap at runtime rather than relying on hardcoded defaults.

---

### `backends/openshift/nextgcore/scc-nextgcore-upf.yaml` (security policy, declarative infra)

**Source pattern:** RESEARCH.md "Pattern 3: Custom SCC for NextGCore UPF" (RESEARCH.md lines 348-383)

```yaml
apiVersion: security.openshift.io/v1
kind: SecurityContextConstraints
metadata:
  name: nextgcore-upf
allowPrivilegedContainer: false
allowHostNetwork: false
allowHostPorts: false
allowHostDirVolumePlugin: false
allowHostIPC: false
allowHostPID: false
readOnlyRootFilesystem: false
runAsUser:
  type: RunAsAny
seLinuxContext:
  type: MustRunAs
fsGroup:
  type: RunAsAny
supplementalGroups:
  type: RunAsAny
allowedCapabilities:
  - NET_ADMIN
  - NET_RAW
requiredDropCapabilities:
  - MKNOD
  - SYS_CHROOT
volumes:
  - configMap
  - emptyDir
  - projected
  - secret
  - downwardAPI
  - persistentVolumeClaim
```

**Binding commands** (imperative, not YAML):
```bash
oc create -f scc-nextgcore-upf.yaml
oc create serviceaccount nextgcore-upf -n otel25-backends
oc adm policy add-scc-to-user nextgcore-upf -z nextgcore-upf -n otel25-backends
```

**Anti-pattern (RESEARCH.md):** Never modify default OpenShift SCCs -- they are reset on cluster upgrade.

---

### `backends/openshift/nextgcore/deployment-nextgcore.yaml` (k8s manifest, request-response)

**Source pattern:** RESEARCH.md "Recommended OpenShift Deployment Topology" (RESEARCH.md lines 631-654)

No complete YAML manifest exists in RESEARCH.md for this file. The planner should construct it from:

1. **Topology (RESEARCH.md lines 631-654):** Three deployment units -- core NFs pod, UPF pod (separate for SCC), nextgsim pod (separate for lifecycle)
2. **Simpler Phase 1 alternative (RESEARCH.md line 654):** All NFs in a single Pod with shared networking, init containers for startup order (NRF first)
3. **Conversion guidance (RESEARCH.md lines 618-627):** Docker Compose to OpenShift conversion requires replacing hardcoded IPs (172.23.0.0/24) with Service DNS names, Docker volumes with ConfigMap mounts, `depends_on` with init containers or startup probes

**Key constraints:**
- UPF container must use `serviceAccountName: nextgcore-upf` (bound to custom SCC)
- NRF must start first (other NFs register with it)
- NextGCore uses userspace SCTP -- no kernel SCTP MachineConfig needed
- Check NextGCore's `k8s/` directory at execution time (Assumption A1) -- if usable, adapt those manifests rather than writing from scratch

---

### `backends/openshift/nextgcore/service-nwdaf.yaml` (k8s manifest, request-response)

**Standard ClusterIP Service exposing NWDAF port 8080.** Follow the same Service pattern as the Prism services but targeting the NextGCore NWDAF container:

```yaml
apiVersion: v1
kind: Service
metadata:
  name: nextgcore-nwdaf
  namespace: otel25-backends
spec:
  selector:
    app: nextgcore       # Must match the NextGCore pod labels
  ports:
  - port: 8080
    targetPort: 8080
    protocol: TCP
  type: ClusterIP
```

---

### `backends/nextgcore/docker-compose.local.yaml` (compose config, orchestration)

**Source pattern:** RESEARCH.md "NextGCore Local Validation with Podman" (RESEARCH.md lines 472-503)

This file is either:
- A verbatim copy/fork of NextGCore's `docker/rust/docker-compose.yml` with any local adjustments, OR
- A thin wrapper referencing the upstream compose file

**Runtime approach (RESEARCH.md lines 477-481):**
```bash
# Use docker-compose binary against Podman socket
# Enable socket: systemctl --user enable --now podman.socket
# Set DOCKER_HOST=unix://$XDG_RUNTIME_DIR/podman/podman.sock
cd /tmp/nextgcore/docker/rust
docker-compose -f docker-compose.yml up -d
```

**Networking pitfall (RESEARCH.md Pitfall 3):** podman-compose breaks NextGCore's custom bridge networking (172.23.0.0/24). Use `docker-compose` v5.0.2 against Podman socket, NOT podman-compose.

---

### `backends/scripts/validate-mocks.sh` (test script, request-response)

**Source pattern:** RESEARCH.md "Standalone Validation Script" (RESEARCH.md lines 526-569)

```bash
#!/usr/bin/env bash
# validate-mocks.sh -- Verify Prism mock responses match OpenAPI specs
set -euo pipefail

SPECS=(
  "tmf642|http://prism-tmf642:4010|/alarm|GET"
  "tmf628|http://prism-tmf628:4010|/measurementCollectionJob|GET"
  "tmf621|http://prism-tmf621:4010|/troubleTicket|GET"
  "camara|http://prism-camara:4010|/verify|POST"
)

PASS=0; FAIL=0
for entry in "${SPECS[@]}"; do
  IFS='|' read -r name base path method <<< "$entry"
  echo "Validating $name: $method $base$path"
  RESPONSE=$(curl -s -w "\n%{http_code}" "$base$path" \
    -H "Prefer: dynamic=true" \
    -X "$method" --max-time 10 2>/dev/null || echo -e "\n000")
  HTTP_CODE=$(echo "$RESPONSE" | tail -1)
  BODY=$(echo "$RESPONSE" | sed '$d')
  
  if [[ "$HTTP_CODE" =~ ^2 ]]; then
    if echo "$BODY" | jq . >/dev/null 2>&1; then
      echo "  PASS: $HTTP_CODE, valid JSON"
      ((PASS++))
    else
      echo "  FAIL: $HTTP_CODE, invalid JSON body"
      ((FAIL++))
    fi
  else
    echo "  FAIL: HTTP $HTTP_CODE"
    ((FAIL++))
  fi
done

echo ""
echo "Results: $PASS passed, $FAIL failed"
[[ $FAIL -eq 0 ]] && exit 0 || exit 1
```

**Validation strategy (RESEARCH.md "Schema Validation Strategy"):**
- Do NOT use Prism validation-proxy to validate Prism's own output -- that is circular and tautological
- Test HTTP reachability (2xx status), valid JSON structure, dynamic variation, and error simulation
- Prism validation-proxy becomes useful in Phase 2+ when validating real MCP server requests

---

### `backends/scripts/verify-routing.sh` (test script, request-response)

**Source pattern:** RESEARCH.md "Pattern 2" -- Verification script (RESEARCH.md lines 319-339)

```bash
#!/usr/bin/env bash
# verify-routing.sh -- Read ConfigMap, call each backend, verify responses
set -euo pipefail

NAMESPACE="otel25-backends"
CM_NAME="backend-routing"

for KEY in TMF642_BASE_URL TMF628_BASE_URL TMF621_BASE_URL CAMARA_BASE_URL CAMARA_RETRIEVAL_BASE_URL NWDAF_BASE_URL; do
  URL=$(oc get configmap "$CM_NAME" -n "$NAMESPACE" -o jsonpath="{.data.$KEY}")
  echo "Testing $KEY -> $URL"
  HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" "$URL/" --max-time 10 || echo "000")
  if [[ "$HTTP_CODE" =~ ^2 ]]; then
    echo "  OK ($HTTP_CODE)"
  else
    echo "  FAIL ($HTTP_CODE)"
    exit 1
  fi
done
echo "All backends responding."
```

**D-16 extension:** The full test should also flip a ConfigMap value (e.g., swap TMF642 from mock to a different URL), re-read, and confirm the script hits the new backend. This proves the switching contract works.

---

### `backends/scripts/check-nwdaf.sh` (smoke test, request-response)

**Source pattern:** RESEARCH.md "NextGCore Local Validation" (RESEARCH.md lines 496-503) and Validation Architecture "Wave 0 Gaps"

No complete script exists in RESEARCH.md. Construct from these curl patterns:

```bash
#!/usr/bin/env bash
# check-nwdaf.sh -- Smoke test NWDAF analytics endpoint
set -euo pipefail

NWDAF_URL="${NWDAF_BASE_URL:-http://nextgcore-nwdaf:8080}"

echo "Testing NWDAF AnalyticsInfo endpoint..."
RESPONSE=$(curl -s -w "\n%{http_code}" \
  "$NWDAF_URL/nnwdaf-analyticsinfo/v1/analytics?event-id=LOAD_LEVEL_INFORMATION" \
  --max-time 10 2>/dev/null || echo -e "\n000")
HTTP_CODE=$(echo "$RESPONSE" | tail -1)

if [[ "$HTTP_CODE" =~ ^2 ]]; then
  echo "  PASS: NWDAF responded with $HTTP_CODE"
else
  echo "  FAIL: NWDAF returned $HTTP_CODE (may need fallback to Prism mock per D-10)"
  exit 1
fi
```

**Key constraints:**
- NWDAF endpoint path may differ (Assumption A4) -- verify against NextGCore at execution time
- Use one-shot analytics queries, not subscriptions (RESEARCH.md Pitfall 2 -- subscriptions are memory-only, lost on restart)
- If NWDAF returns errors/empty, trigger timebox-then-fallback (D-10)
- **IMPORTANT:** The hardcoded default (`http://nextgcore-nwdaf:8080`) is only correct for Path A (NextGCore). When Path B (Prism fallback) is taken, the NWDAF Prism runs on port 4010. Callers MUST export `NWDAF_BASE_URL` from the ConfigMap before invoking this script to ensure the correct port is used regardless of path. Pattern: `export NWDAF_BASE_URL=$(oc get configmap backend-routing -n otel25-backends -o jsonpath='{.data.NWDAF_BASE_URL}')`

---

## Shared Patterns

### Pattern: Namespace Consistency
**Apply to:** All OpenShift manifest files
All resources use namespace `otel25-backends`. Every manifest's `metadata.namespace` field must match.

### Pattern: ClusterIP Services (No External Routes)
**Source:** RESEARCH.md Security Domain -- "Exposed mock endpoints outside cluster" threat
**Apply to:** All Service manifests (`prism-tmf642.yaml`, `prism-tmf628.yaml`, `prism-tmf621.yaml`, `prism-camara.yaml`, `prism-camara-retrieval.yaml`, `service-nwdaf.yaml`)
All services use `type: ClusterIP`. No Routes are created for mock backends unless explicitly needed for debugging. This prevents information disclosure of mock data outside the cluster.

### Pattern: Resource Limits
**Source:** RESEARCH.md Prism Deployment pattern (lines 260-267)
**Apply to:** All Prism Deployment manifests
```yaml
resources:
  requests:
    cpu: 100m
    memory: 128Mi
  limits:
    cpu: 250m
    memory: 256Mi
```

### Pattern: Bash Script Header
**Apply to:** All scripts in `backends/scripts/`
```bash
#!/usr/bin/env bash
set -euo pipefail
```
All scripts use strict mode (`-e` exit on error, `-u` undefined variable error, `-o pipefail` pipe failure propagation).

### Pattern: Consistent Label Scheme
**Apply to:** All Deployment and Service manifests
```yaml
labels:
  app: <deployment-name>     # e.g., prism-tmf642
  api: <api-identifier>      # e.g., tmf642, nwdaf
```
Labels are used for Service selectors and for `oc get pods -l api=tmf642` filtering.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| ALL 21 files | various | various | Greenfield repository -- no existing application code, Dockerfiles, Kubernetes/OpenShift manifests, or scripts exist. RESEARCH.md code examples serve as the sole pattern source. |

**Planner guidance:** Since no in-repo analogs exist, the planner should treat RESEARCH.md's code examples (Patterns 1-3, Code Examples section, and Validation Architecture) as the canonical patterns. Each pattern assignment above extracts the specific RESEARCH.md section and line range to copy from.

---

## Metadata

**Analog search scope:** Entire repository (`/Users/ravsharm/Desktop/Work/freewheeling/OTel_agentic_improvements/`)
**Files scanned:** All non-`.git` files -- only markdown documents and `.planning/config.json` found
**Pattern extraction source:** `01-RESEARCH.md` code examples (no in-repo code exists)
**Pattern extraction date:** 2026-09-27
**Revision date:** 2026-10-02 (checker-driven updates: 5 Prism manifests, tcpSocket CAMARA probes, 6 ConfigMap keys, mounted-file contract, NWDAF port single-source-of-truth)
