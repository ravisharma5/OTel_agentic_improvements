# Phase 2: MCP Tooling Foundation - Pattern Map

**Mapped:** 2026-10-02
**Files analyzed:** 14 new/modified files
**Analogs found:** 11 / 14

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `mcp/mcp-telecom/pyproject.toml` | config | -- | *(upstream MCP-Telecom)* | external |
| `mcp/mcp-telecom/src/mcp_telecom/server.py` | service | request-response | *(upstream MCP-Telecom)* | external |
| `mcp/mcp-telecom/LICENSE` | config | -- | *(upstream MIT license)* | external |
| `mcp/mcp-telecom/NOTICE` | config | -- | -- | none |
| `mcp/mcp-telecom/devices.yaml.example` | config | -- | -- | none |
| `mcp/mcp-telecom/command_allowlist.yaml` | config | -- | -- | none |
| `mcp/mcp-telecom/Dockerfile` | config | -- | `backends/prism/Dockerfile` | role-match |
| `mcp/openshift/namespace.yaml` | config | -- | `backends/openshift/namespace.yaml` | exact |
| `mcp/openshift/mcp-telecom-deployment.yaml` | config | -- | `backends/openshift/prism-tmf642.yaml` | exact |
| `mcp/openshift/mcp-telecom-secret.yaml` | config | -- | -- | none (no Secret analog in Phase 1) |
| `mcp/tooling/openapi_to_mcp.py` | utility | transform | -- | none |
| `mcp/tooling/allowlist_schema.py` | model | -- | -- | none |
| `mcp/tooling/templates/server_template.py.j2` | config | transform | -- | none |
| `scripts/verify-mcp-telecom.sh` | utility | request-response | `backends/scripts/verify-routing.sh` | role-match |

## Pattern Assignments

### `mcp/mcp-telecom/Dockerfile` (config, container image)

**Analog:** `backends/prism/Dockerfile`

The Phase 1 Dockerfile is a Node.js/Prism image. Phase 2's is Python/FastMCP. The structural pattern to follow is the same: decision-traced comments, build-arg validation, baked-in artifacts, explicit entrypoint.

**Decision-traced header comment pattern** (lines 1-6):
```dockerfile
# Parameterized Prism mock server image
# Build context: backends/ directory
# Usage: podman build --build-arg SPEC_FILE=specs/<spec-file> -f prism/Dockerfile -t prism-<api> backends/
#
# Per D-04 (use Prism), D-06 (vendor specs into repo, bake into images per RESEARCH.md Pattern 1),
# D-08 (dynamic schema-based mock generation, bind 0.0.0.0)
```

**Build-arg validation pattern** (lines 11-12):
```dockerfile
ARG SPEC_FILE
RUN test -n "$SPEC_FILE" || (echo "ERROR: SPEC_FILE build arg is required" && exit 1)
```

**Bake-artifact-into-image pattern** (line 15):
```dockerfile
# Bake the vendored spec into the image (D-06: no network fetch at deploy time)
COPY ${SPEC_FILE} /specs/api.yaml
```

**Key adaptation:** Phase 2's Dockerfile uses `python:3.12-slim` base, `uv` for dependency install, copies `pyproject.toml` + `src/` + config scaffolds. No build-arg needed (single server, not parameterized). Must include non-root user for OpenShift arbitrary UID support.

---

### `mcp/openshift/namespace.yaml` (config, namespace)

**Analog:** `backends/openshift/namespace.yaml`

**Exact pattern to copy** (full file, lines 1-6):
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: otel25-backends
  labels:
    purpose: phase-1-backends
```

**Key adaptation:** Change `name: otel25-mcp`, `purpose: phase-2-mcp`. Add `layer: mcp` label for consistency with the deployment label scheme.

---

### `mcp/openshift/mcp-telecom-deployment.yaml` (config, Deployment+Service)

**Analog:** `backends/openshift/prism-tmf642.yaml`

This is the strongest analog. The Prism deployment YAMLs establish the exact structure Phase 2 should follow: combined Deployment+Service in one file, consistent label scheme, ClusterIP service type, resource requests/limits, probe configuration.

**Full Deployment pattern** (lines 1-47):
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
        api: tmf642
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
            path: /alarm
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

**Full Service pattern** (lines 48-65):
```yaml
---
apiVersion: v1
kind: Service
metadata:
  name: prism-tmf642
  namespace: otel25-backends
  labels:
    app: prism-tmf642
    api: tmf642
spec:
  selector:
    app: prism-tmf642
  ports:
  - port: 4010
    targetPort: 4010
    protocol: TCP
  type: ClusterIP
```

**Key adaptations:**
- Namespace: `otel25-mcp` instead of `otel25-backends`
- Label scheme: `app: mcp-telecom`, `layer: mcp` instead of `api: tmf642`
- Image registry path: `image-registry.openshift-image-registry.svc:5000/otel25-mcp/mcp-telecom:latest`
- Port: `8000` instead of `4010`
- Container name: `mcp-telecom` instead of `prism`
- Resources: higher limits for Python (cpu 250m/500m, memory 256Mi/512Mi per RESEARCH.md)
- Probes: liveness uses `tcpSocket` port 8000 (like `prism-camara.yaml` pattern, lines 38-40); readiness uses either a custom `/healthz` endpoint or exec probe (see RESEARCH.md Pitfall 2 -- GET to Streamable HTTP `/mcp` returns 405)
- No `env` for `NODE_ENV` -- Python server, not Node.js

**Note on probe pattern variation:** Phase 1 has two probe styles. `prism-tmf642.yaml` uses `httpGet` for both probes (works because Prism serves GET). `prism-camara.yaml` uses `tcpSocket` for both (lines 37-45). Phase 2 should use `tcpSocket` for liveness (process-up check per D-20) and either a custom health endpoint or exec probe for readiness (MCP endpoint responds per D-20).

**tcpSocket probe pattern from `prism-camara.yaml`** (lines 37-45):
```yaml
        readinessProbe:
          tcpSocket:
            port: 4010
          initialDelaySeconds: 5
          periodSeconds: 10
        livenessProbe:
          tcpSocket:
            port: 4010
          initialDelaySeconds: 10
          periodSeconds: 30
```

---

### `scripts/verify-mcp-telecom.sh` (utility, verification script)

**Analog:** `backends/scripts/verify-routing.sh` (primary), `backends/scripts/validate-mocks.sh` (secondary)

Phase 2's verification script (D-08) must prove the full MCP protocol round-trip: `tools/list` + one representative tool invocation. These two Phase 1 scripts establish the verification pattern.

**Script header and structure pattern from `verify-routing.sh`** (lines 1-13):
```bash
#!/usr/bin/env bash
# verify-routing.sh -- Verify ConfigMap-based backend routing (D-16, BACK-03)
#
# Reads the backend-routing ConfigMap from OpenShift, curls each URL,
# verifies 2xx responses, then demonstrates the switching contract by
# patching one key to a bad URL and confirming the change propagated.
#
# Usage: NAMESPACE=otel25-backends ./verify-routing.sh
#        Requires: oc CLI authenticated to the target cluster

set -euo pipefail

NAMESPACE="${NAMESPACE:-otel25-backends}"
```

**Configurable base URL via env vars from `validate-mocks.sh`** (lines 16-20):
```bash
# Base URLs (configurable via env vars; defaults to in-cluster Service DNS)
TMF642_URL="${TMF642_URL:-http://prism-tmf642.otel25-backends.svc.cluster.local:4010}"
TMF628_URL="${TMF628_URL:-http://prism-tmf628.otel25-backends.svc.cluster.local:4010}"
TMF621_URL="${TMF621_URL:-http://prism-tmf621.otel25-backends.svc.cluster.local:4010}"
```

**PASS/FAIL counter and summary pattern from `validate-mocks.sh`** (lines 32-33, 173-188):
```bash
PASS=0
FAIL=0

# ... test logic ...

echo "=== Results ==="
echo "Endpoints tested: ${#ENDPOINTS[@]}"
echo "Passed: $PASS"
echo "Failed: $FAIL"
echo ""

if [[ $FAIL -eq 0 ]]; then
  echo "OVERALL: PASS"
  exit 0
else
  echo "OVERALL: FAIL"
  exit 1
fi
```

**Multi-level validation pattern from `validate-mocks.sh`** (lines 144-168):
```bash
  # Level 1: HTTP 2xx check (hard gate)
  if [[ "$HTTP_CODE" =~ ^2 ]]; then
    echo "  PASS: HTTP $HTTP_CODE"
  else
    echo "  FAIL: HTTP $HTTP_CODE"
    FAIL=$((FAIL + 1))
    echo ""
    continue
  fi

  # Level 2: Valid JSON check (hard gate)
  if echo "$BODY" | jq . >/dev/null 2>&1; then
    echo "  PASS: valid JSON body"
  else
    echo "  FAIL: invalid JSON body"
    FAIL=$((FAIL + 1))
    echo ""
    continue
  fi
```

**Key adaptations for `verify-mcp-telecom.sh`:**
- Default URL: `http://mcp-telecom.otel25-mcp.svc.cluster.local:8000`
- Namespace: `otel25-mcp`
- Test 1: `tools/list` via Streamable HTTP POST to `/mcp` with JSON-RPC payload `{"jsonrpc":"2.0","method":"tools/list","id":1}`
- Test 2: invoke one representative tool (e.g., `get_device_info`) via POST to `/mcp` with `{"jsonrpc":"2.0","method":"tools/call","params":{"name":"get_device_info","arguments":{...}},"id":2}`
- Level 1: HTTP 200 response from POST
- Level 2: valid JSON-RPC response body
- Level 3: `tools/list` result contains expected number of tools (soft check)
- Tool invocation is expected to fail with connection error (D-07) -- assert the response contains an error result, not a transport failure

---

### `mcp/mcp-telecom/pyproject.toml` (config, dependency manifest)

**Analog:** upstream MCP-Telecom `pyproject.toml` (external, not in codebase)

No in-repo analog. The modification is described precisely in RESEARCH.md Pattern 1: swap `mcp[cli]>=1.0.0` to `fastmcp>=4.0.0` in the `[project.dependencies]` array. All other dependencies remain unchanged.

---

### `mcp/mcp-telecom/src/mcp_telecom/server.py` (service, MCP server entry point)

**Analog:** upstream MCP-Telecom `server.py` (external, not in codebase)

No in-repo analog. The modification is described precisely in RESEARCH.md Pattern 1 -- exactly two changes:
1. Import: `from mcp.server.fastmcp import FastMCP` -> `from fastmcp import FastMCP`
2. Transport: `mcp.run(transport="stdio")` -> `mcp.run(transport="http", host="0.0.0.0", port=8000)`

Plus the health endpoint addition per RESEARCH.md Pitfall 2 (if using `/healthz` readiness probe approach).

---

### `mcp/tooling/openapi_to_mcp.py` (utility, codegen CLI)

**Analog:** none in codebase

This is a new capability with no prior analog. RESEARCH.md Pattern 2 provides the complete design. The CLI reads an OpenAPI spec + YAML allowlist, generates a `server.py` scaffold via templating. Key structural elements from RESEARCH.md:
- Uses `argparse` or similar for CLI interface
- Reads allowlist YAML, maps to `RouteMap` entries
- Renders `server_template.py.j2` (or Python string template) with spec path, route maps, ConfigMap watcher boilerplate
- Outputs a standalone `server.py` file

---

### `mcp/tooling/templates/server_template.py.j2` (config, codegen template)

**Analog:** none in codebase

RESEARCH.md Pattern 2 provides the full generated scaffold structure (lines 277-382 of RESEARCH.md). The template must include:
- Decision-traced header comments with generation metadata
- ConfigMap file-watcher boilerplate (BACK-03 contract, from RESEARCH.md Pattern 3)
- `from_openapi()` call with `RouteMap` filtering
- `mcp_component_fn` customization hook
- `mcp.run(transport="http")` startup

---

## Shared Patterns

### Bash Script Structure
**Source:** `backends/scripts/verify-routing.sh` (lines 1-11)
**Apply to:** `scripts/verify-mcp-telecom.sh`
```bash
#!/usr/bin/env bash
# <script-name> -- <one-line description> (<decision refs>)
#
# <multi-line description of what the script does>
#
# Usage: <usage example>
#        Requires: <prerequisites>

set -euo pipefail

NAMESPACE="${NAMESPACE:-otel25-backends}"
```

### OpenShift Label Scheme
**Source:** `backends/openshift/prism-tmf642.yaml` (lines 4-8, 17-18, 55-57)
**Apply to:** All `mcp/openshift/` manifests
```yaml
# Deployment metadata.labels and template.metadata.labels
  labels:
    app: <workload-name>        # selector label (must match Service selector)
    <domain-key>: <domain-val>  # Phase 1 uses "api: tmf642"; Phase 2 uses "layer: mcp"

# Service spec.selector
  selector:
    app: <workload-name>
```

### OpenShift Image Registry Path Convention
**Source:** `backends/openshift/prism-tmf642.yaml` (line 23)
**Apply to:** `mcp/openshift/mcp-telecom-deployment.yaml`
```yaml
image: image-registry.openshift-image-registry.svc:5000/<namespace>/<image-name>:latest
# Phase 1: image-registry.openshift-image-registry.svc:5000/otel25-backends/prism-tmf642:latest
# Phase 2: image-registry.openshift-image-registry.svc:5000/otel25-mcp/mcp-telecom:latest
```

### Resource Requests/Limits Convention
**Source:** `backends/openshift/prism-tmf642.yaml` (lines 29-34)
**Apply to:** `mcp/openshift/mcp-telecom-deployment.yaml`
```yaml
        resources:
          requests:
            cpu: 100m
            memory: 128Mi
          limits:
            cpu: 250m
            memory: 256Mi
```
Phase 2 should increase these for the Python/FastMCP server (heavier than Node.js Prism): cpu 250m/500m, memory 256Mi/512Mi per RESEARCH.md Pattern 4.

### Verification Script Summary Block
**Source:** `backends/scripts/validate-mocks.sh` (lines 173-188), `backends/scripts/check-nwdaf.sh` (lines 121-127)
**Apply to:** `scripts/verify-mcp-telecom.sh`
```bash
echo "=== <Test Name> Complete ==="
echo "OVERALL: PASS"
exit 0
# or
echo "OVERALL: FAIL"
exit 1
```

### Dockerfile Decision-Trace Comments
**Source:** `backends/prism/Dockerfile` (lines 1-6)
**Apply to:** `mcp/mcp-telecom/Dockerfile`

Every non-trivial Dockerfile directive should trace back to the CONTEXT.md decision that requires it, e.g.:
```dockerfile
# Per D-01 (HTTP transport), D-02 (HTTP-only, no stdio), D-03 (Streamable HTTP)
```

### ConfigMap Volume-Mount Consumer Contract
**Source:** `backends/openshift/configmap-backend-routing.yaml` (lines 1-32)
**Apply to:** `mcp/tooling/templates/server_template.py.j2` (baked into generated scaffolds per D-16)

The contract requires:
1. Mount the ConfigMap as a volume (not envFrom)
2. Implement file-watching or periodic re-reading of the mounted file
3. Use the mounted file contents as the backend URL at request time

RESEARCH.md Pattern 3 provides the Python implementation (mtime-based polling in a daemon thread). This boilerplate is baked into every generated scaffold.

## No Analog Found

Files with no close match in the codebase (planner should use RESEARCH.md patterns instead):

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `mcp/mcp-telecom/NOTICE` | config | -- | No attribution files exist in Phase 1; follow standard Apache/MIT NOTICE convention |
| `mcp/mcp-telecom/devices.yaml.example` | config | -- | New config shape; no device-inventory analog exists. D-10 specifies OpenShift Secret references for credentials |
| `mcp/mcp-telecom/command_allowlist.yaml` | config | -- | New config shape; no command-allowlist analog exists. D-10a specifies config-driven, empty/permissive placeholder |
| `mcp/openshift/mcp-telecom-secret.yaml` | config | -- | No OpenShift Secret manifests in Phase 1. Standard K8s Secret with `stringData` placeholder |
| `mcp/tooling/openapi_to_mcp.py` | utility | transform | No CLI codegen tools exist in the codebase. Use RESEARCH.md Pattern 2 design |
| `mcp/tooling/allowlist_schema.py` | model | -- | No Pydantic config models exist. Use RESEARCH.md D-12 allowlist schema design |
| `mcp/tooling/templates/server_template.py.j2` | config | transform | No Jinja2/codegen templates exist. Use RESEARCH.md Pattern 2 generated scaffold structure |

## Metadata

**Analog search scope:** `backends/` directory (OpenShift manifests, Dockerfile, scripts, specs)
**Files scanned:** 16 (all files under `backends/`)
**Pattern extraction date:** 2026-10-02
