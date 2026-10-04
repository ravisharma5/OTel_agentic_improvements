# Phase 3: MCP Domain Servers and Gateway - Pattern Map

**Mapped:** 2026-10-04
**Files analyzed:** 42 new files
**Analogs found:** 42 / 42

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `mcp/tmf642/server.py` | service | request-response | `mcp/tooling/openapi_to_mcp.py` (generated scaffold template) | exact |
| `mcp/tmf642/allowlist.yaml` | config | -- | `mcp/tooling/tests/camara_allowlist.yaml` | exact |
| `mcp/tmf642/Dockerfile` | config | -- | `mcp/mcp-telecom/Dockerfile` | exact |
| `mcp/tmf628/server.py` | service | request-response | `mcp/tooling/openapi_to_mcp.py` (generated scaffold template) | exact |
| `mcp/tmf628/allowlist.yaml` | config | -- | `mcp/tooling/tests/camara_allowlist.yaml` | exact |
| `mcp/tmf628/Dockerfile` | config | -- | `mcp/mcp-telecom/Dockerfile` | exact |
| `mcp/tmf621/server.py` | service | request-response | `mcp/tooling/openapi_to_mcp.py` (generated scaffold template) | exact |
| `mcp/tmf621/allowlist.yaml` | config | -- | `mcp/tooling/tests/camara_allowlist.yaml` | exact |
| `mcp/tmf621/Dockerfile` | config | -- | `mcp/mcp-telecom/Dockerfile` | exact |
| `mcp/nwdaf/server.py` | service | request-response | `mcp/tooling/openapi_to_mcp.py` (scaffold) + `mcp/mcp-telecom/src/mcp_telecom/server.py` (mount/composition) | role-match |
| `mcp/nwdaf/allowlist_analytics.yaml` | config | -- | `mcp/tooling/tests/camara_allowlist.yaml` | exact |
| `mcp/nwdaf/allowlist_events.yaml` | config | -- | `mcp/tooling/tests/camara_allowlist.yaml` | exact |
| `mcp/nwdaf/Dockerfile` | config | -- | `mcp/mcp-telecom/Dockerfile` | exact |
| `mcp/camara/server.py` | service | request-response | `mcp/tooling/openapi_to_mcp.py` (scaffold) + `mcp/mcp-telecom/src/mcp_telecom/server.py` (mount/composition) | role-match |
| `mcp/camara/allowlist_verify.yaml` | config | -- | `mcp/tooling/tests/camara_allowlist.yaml` | exact |
| `mcp/camara/allowlist_retrieve.yaml` | config | -- | `mcp/tooling/tests/camara_allowlist.yaml` | exact |
| `mcp/camara/Dockerfile` | config | -- | `mcp/mcp-telecom/Dockerfile` | exact |
| `mcp/openshift/mcp-tmf642-deployment.yaml` | config | -- | `mcp/openshift/mcp-telecom-deployment.yaml` | exact |
| `mcp/openshift/mcp-tmf628-deployment.yaml` | config | -- | `mcp/openshift/mcp-telecom-deployment.yaml` | exact |
| `mcp/openshift/mcp-tmf621-deployment.yaml` | config | -- | `mcp/openshift/mcp-telecom-deployment.yaml` | exact |
| `mcp/openshift/mcp-nwdaf-deployment.yaml` | config | -- | `mcp/openshift/mcp-telecom-deployment.yaml` | exact |
| `mcp/openshift/mcp-camara-deployment.yaml` | config | -- | `mcp/openshift/mcp-telecom-deployment.yaml` | exact |
| `gateway/openshift/namespace.yaml` | config | -- | `mcp/openshift/namespace.yaml` | exact |
| `gateway/openshift/ossm-subscription.yaml` | config | -- | (no analog -- OLM Subscription CRD) | no-analog |
| `gateway/openshift/istio-cni.yaml` | config | -- | (no analog -- Istio CRD) | no-analog |
| `gateway/openshift/istio.yaml` | config | -- | (no analog -- Istio CRD) | no-analog |
| `gateway/openshift/cert-manager-subscription.yaml` | config | -- | (no analog -- OLM Subscription CRD) | no-analog |
| `gateway/openshift/mcp-gateway-subscription.yaml` | config | -- | (no analog -- OLM Subscription CRD) | no-analog |
| `gateway/openshift/gateway.yaml` | config | -- | (no analog -- Gateway API CRD) | no-analog |
| `gateway/openshift/mcp-gateway-extension.yaml` | config | -- | (no analog -- RHCL CRD) | no-analog |
| `gateway/openshift/reference-grant.yaml` | config | -- | (no analog -- Gateway API CRD) | no-analog |
| `gateway/openshift/mcpsr-tmf642.yaml` | config | -- | (no analog -- RHCL CRD) | no-analog |
| `gateway/openshift/mcpsr-tmf628.yaml` | config | -- | `gateway/openshift/mcpsr-tmf642.yaml` (sibling) | exact |
| `gateway/openshift/mcpsr-tmf621.yaml` | config | -- | `gateway/openshift/mcpsr-tmf642.yaml` (sibling) | exact |
| `gateway/openshift/mcpsr-nwdaf.yaml` | config | -- | `gateway/openshift/mcpsr-tmf642.yaml` (sibling) | exact |
| `gateway/openshift/mcpsr-camara.yaml` | config | -- | `gateway/openshift/mcpsr-tmf642.yaml` (sibling) | exact |
| `gateway/openshift/mcpsr-telecom.yaml` | config | -- | `gateway/openshift/mcpsr-tmf642.yaml` (sibling) | exact |
| `gateway/openshift/mcpvs-tmf.yaml` | config | -- | (no analog -- RHCL CRD) | no-analog |
| `gateway/openshift/mcpvs-nwdaf.yaml` | config | -- | `gateway/openshift/mcpvs-tmf.yaml` (sibling) | exact |
| `gateway/openshift/mcpvs-camara.yaml` | config | -- | `gateway/openshift/mcpvs-tmf.yaml` (sibling) | exact |
| `gateway/openshift/mcpvs-infra.yaml` | config | -- | `gateway/openshift/mcpvs-tmf.yaml` (sibling) | exact |
| `gateway/openshift/auth-policy.yaml` | config | -- | (no analog -- RHCL AuthPolicy CRD) | no-analog |
| `scripts/verify-domain-tools.sh` | utility | request-response | (no analog -- new verification script) | no-analog |
| `scripts/verify-gateway.sh` | utility | request-response | (no analog -- new verification script) | no-analog |

## Pattern Assignments

### `mcp/tmf642/server.py` (service, request-response) -- and TMF628, TMF621 follow same pattern

**Analog:** Generated scaffold template inside `mcp/tooling/openapi_to_mcp.py`

These files are the OUTPUT of the conversion CLI. The planner runs `python openapi_to_mcp.py --spec <spec> --allowlist <allowlist> --output <server.py>` and then hand-curates the result. The generated code follows this exact pattern:

**Generated scaffold structure** (`mcp/tooling/openapi_to_mcp.py` lines 37-158, the SCAFFOLD_TEMPLATE):
```python
# Auto-generated by mcp/tooling/openapi_to_mcp.py
# Spec: $spec_filename
# Allowlist: $allowlist_filename
# Generated: $generation_timestamp

import os
import json
import threading
import time
from pathlib import Path
from fastmcp import FastMCP
from fastmcp.server.providers.openapi import RouteMap, MCPType, OpenAPITool
import httpx2
import yaml


# --- ConfigMap file-watcher (BACK-03 contract) ---
BACKEND_ROUTING_PATH = os.environ.get(
    "BACKEND_ROUTING_FILE", "/config/backend-routing/$backend_env_var"
)
_backend_url_lock = threading.Lock()
_backend_url = "http://localhost:4010"  # default fallback


def _load_backend_url():
    global _backend_url
    try:
        url = Path(BACKEND_ROUTING_PATH).read_text().strip()
        if url and (url.startswith("http://") or url.startswith("https://")):
            with _backend_url_lock:
                _backend_url = url
            client.base_url = url
    except FileNotFoundError:
        pass


def get_backend_url() -> str:
    with _backend_url_lock:
        return _backend_url


def _start_config_watcher():
    config_path = Path(BACKEND_ROUTING_PATH)
    last_mtime = 0.0

    def _poll():
        nonlocal last_mtime
        while True:
            try:
                current_mtime = config_path.stat().st_mtime
                if current_mtime != last_mtime:
                    last_mtime = current_mtime
                    _load_backend_url()
            except FileNotFoundError:
                pass
            time.sleep(5)

    t = threading.Thread(target=_poll, daemon=True)
    t.start()


# --- OpenAPI Server ---
SPEC_PATH = Path("$spec_path")

route_maps = [
$route_maps_code
    # Exclude everything else (catch-all)
    RouteMap(mcp_type=MCPType.EXCLUDE),
]


def customize_components(route, component):
    if isinstance(component, OpenAPITool):
        pass


spec_dict = yaml.safe_load(SPEC_PATH.read_text())
client = httpx2.AsyncClient(base_url=get_backend_url())

mcp = FastMCP.from_openapi(
    openapi_spec=spec_dict,
    client=client,
    route_maps=route_maps,
    mcp_component_fn=customize_components,
)

# --- Startup ---
_load_backend_url()
_start_config_watcher()

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000, stateless_http=True)
```

**CLI invocation pattern** (`mcp/tooling/openapi_to_mcp.py` lines 183-247):
```bash
cd mcp/tooling
python openapi_to_mcp.py \
  --spec <path-to-spec> \
  --allowlist <path-to-allowlist> \
  --output <path-to-server.py>
```

**Hand-curation additions** (learned from `mcp/mcp-telecom/src/mcp_telecom/server.py` lines 1828-1856):

After generation, each domain server needs a `/healthz` endpoint and uvicorn runner added, matching MCP-Telecom's pattern:
```python
def create_app():
    """Create the ASGI app with custom routes (e.g. /healthz)."""
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def healthz(request):
        return JSONResponse({"status": "ok"})

    app = mcp.http_app()
    app.router.routes.append(Route("/healthz", healthz))
    return app


def main():
    """Run the domain MCP server over Streamable HTTP."""
    import uvicorn
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
```

---

### `mcp/nwdaf/server.py` and `mcp/camara/server.py` (service, request-response -- multi-spec composition)

**Analog 1:** Generated scaffold template in `mcp/tooling/openapi_to_mcp.py` lines 37-158
**Analog 2:** FastMCP mount() usage from RESEARCH.md Pattern 3

These are multi-spec servers (NWDAF: 2 specs merged, CAMARA: 2 specs merged). The CLI is invoked twice per domain, then the two generated scaffolds are merged into one `server.py`. The composition uses either:

**Option A -- mount() composition (from RESEARCH.md Pattern 3):**
```python
from fastmcp import FastMCP
import httpx2

analytics_client = httpx2.AsyncClient(base_url=get_backend_url("NWDAF_BASE_URL"))
events_client = httpx2.AsyncClient(base_url=get_backend_url("NWDAF_BASE_URL"))

analytics_mcp = FastMCP.from_openapi(
    openapi_spec=analytics_spec,
    client=analytics_client,
    route_maps=analytics_route_maps,
)

events_mcp = FastMCP.from_openapi(
    openapi_spec=events_spec,
    client=events_client,
    route_maps=events_route_maps,
)

mcp = FastMCP("NWDAF")
mcp.mount("analytics", analytics_mcp)
mcp.mount("events", events_mcp)
```

**Option B -- explicit @mcp.tool() decorators (for small tool counts):**
```python
# From mcp/mcp-telecom/src/mcp_telecom/server.py lines 53-73 (tool decorator pattern)
@mcp.tool()
def show_bgp_summary(device: str) -> str:
    """Show BGP neighbor summary on a network device.
    ...
    """
    try:
        # ... tool logic ...
        return output
    except Exception as e:
        return f"Error: {e}"
```

The ConfigMap watcher, `/healthz` endpoint, and uvicorn runner from the single-spec servers apply identically.

---

### `mcp/tmf642/allowlist.yaml` (config) -- and all other allowlist.yaml files

**Analog:** `mcp/tooling/tests/camara_allowlist.yaml`

**Full file** (lines 1-5):
```yaml
server_name: "camara-location"
spec_path: "../../backends/specs/camara_location_verification.yaml"
backend_env_var: "CAMARA_BASE_URL"
operations:
  - path: "/verify"
    methods: ["POST"]
```

**Schema reference:** `mcp/tooling/allowlist_schema.py` (lines 39-63):
```python
class AllowlistConfig(BaseModel):
    server_name: str = Field(
        ...,
        description="FastMCP server name used in the generated scaffold",
    )
    spec_path: str = Field(
        ...,
        description="Path to the OpenAPI spec file (relative or absolute)",
    )
    backend_env_var: str = Field(
        ...,
        description="ConfigMap key name for backend URL, e.g. 'CAMARA_BASE_URL'",
    )
    operations: list[OperationFilter] = Field(
        ...,
        description="Operations to include as MCP tools; unlisted operations are excluded",
    )
```

Each new domain server needs its own allowlist with `server_name`, `spec_path`, `backend_env_var` (matching a key in `backends/openshift/configmap-backend-routing.yaml`), and the curated `operations` list.

---

### `mcp/tmf642/Dockerfile` (config) -- and all domain server Dockerfiles

**Analog:** `mcp/mcp-telecom/Dockerfile` (lines 1-49)

```dockerfile
FROM python:3.12-slim

# Copy uv for fast, reproducible dependency installation
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

# Layer caching: copy dependency manifests first, install, then copy source
COPY pyproject.toml uv.lock README.md ./

# Install production dependencies only (frozen lockfile, no dev deps)
RUN uv sync --no-dev --frozen

# Copy source code
COPY src/ ./src/
# (domain servers: copy server.py, specs/, allowlist.yaml instead)

# OpenShift arbitrary-UID support:
RUN chgrp -R 0 /app && chmod -R g=u /app

# Create explicit cache directories for uv and Python, also group-writable
RUN mkdir -p /app/.cache /app/.local && chgrp -R 0 /app/.cache /app/.local && chmod -R g=u /app/.cache /app/.local

# Redirect uv cache to a writable location
ENV UV_CACHE_DIR=/app/.cache/uv

# Prevent __pycache__ write attempts entirely
ENV PYTHONDONTWRITEBYTECODE=1

# Use numeric UID (OpenShift convention for arbitrary-UID images)
USER 1001

EXPOSE 8000

CMD ["uv", "run", "python", "server.py"]
```

Key differences from MCP-Telecom Dockerfile:
- Domain servers copy `server.py`, `specs/`, and allowlist YAML (not `src/` package)
- CMD runs `python server.py` directly (no pyproject.toml `[project.scripts]` entry point needed for generated scaffolds)
- No `devices.yaml.example` or `command_allowlist.yaml` copies

---

### `mcp/openshift/mcp-tmf642-deployment.yaml` (config) -- and all domain server deployment YAMLs

**Analog:** `mcp/openshift/mcp-telecom-deployment.yaml` (lines 1-61)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-telecom
  namespace: otel25-mcp
  labels:
    app: mcp-telecom
    layer: mcp
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mcp-telecom
  template:
    metadata:
      labels:
        app: mcp-telecom
        layer: mcp
    spec:
      containers:
      - name: mcp-telecom
        image: image-registry.openshift-image-registry.svc:5000/otel25-mcp/mcp-telecom:latest
        ports:
        - containerPort: 8000
          protocol: TCP
        resources:
          requests:
            cpu: 250m
            memory: 256Mi
          limits:
            cpu: 500m
            memory: 512Mi
        readinessProbe:
          httpGet:
            path: /healthz
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
        livenessProbe:
          tcpSocket:
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 30
---
apiVersion: v1
kind: Service
metadata:
  name: mcp-telecom
  namespace: otel25-mcp
  labels:
    app: mcp-telecom
    layer: mcp
spec:
  selector:
    app: mcp-telecom
  ports:
  - port: 8000
    targetPort: 8000
    protocol: TCP
  type: ClusterIP
```

**Adaptations per domain server:**
- Replace `mcp-telecom` with `mcp-tmf642` / `mcp-tmf628` / `mcp-tmf621` / `mcp-nwdaf` / `mcp-camara` in metadata.name, labels, selector, container name, image ref, and Service
- Add `domain: tmf` / `domain: nwdaf` / `domain: camara` label (per RESEARCH.md Example 4)
- Add `volumeMounts` for `backend-routing` ConfigMap (the MCP-Telecom deployment does NOT have this because it has no backend -- D-07/D-09, but the 5 new domain servers DO need it per BACK-03):
```yaml
        volumeMounts:
        - name: backend-routing
          mountPath: /config/backend-routing
          readOnly: true
      volumes:
      - name: backend-routing
        configMap:
          name: backend-routing
```

Note: The ConfigMap `backend-routing` lives in `otel25-backends` namespace but is mounted into pods in `otel25-mcp`. This requires the ConfigMap to be either (a) duplicated into `otel25-mcp` or (b) referenced cross-namespace. Standard Kubernetes ConfigMap volume mounts only work within the same namespace, so the planner needs to either create a copy of the ConfigMap in `otel25-mcp` or use a projected volume with a cross-namespace fetch mechanism.

---

### `gateway/openshift/namespace.yaml` (config)

**Analog:** `mcp/openshift/namespace.yaml` (lines 1-6) and `backends/openshift/namespace.yaml` (lines 1-5)

```yaml
# mcp/openshift/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: otel25-mcp
  labels:
    purpose: phase-2-mcp
    layer: mcp
```

```yaml
# backends/openshift/namespace.yaml
apiVersion: v1
kind: Namespace
metadata:
  name: otel25-backends
  labels:
    purpose: phase-1-backends
```

**Pattern:** Each namespace gets a `purpose` label with `phase-N-description` and optionally a `layer` label. The gateway namespace should be:
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: otel25-gateway
  labels:
    purpose: phase-3-gateway
    layer: gateway
```

---

### `gateway/openshift/mcpsr-*.yaml` (config -- MCPServerRegistration CRDs)

**Analog:** None in codebase (new RHCL CRD type). Pattern from RESEARCH.md.

**Pattern from RESEARCH.md Pattern 1** (lines 300-316):
```yaml
apiVersion: mcp.kuadrant.io/v1alpha1
kind: MCPServerRegistration
metadata:
  name: tmf642
  namespace: otel25-gateway
spec:
  prefix: tmf642
  targetRef:
    group: gateway.networking.k8s.io
    kind: HTTPRoute
    name: mcp-tmf642-route
```

All 6 MCPServerRegistration files (tmf642, tmf628, tmf621, nwdaf, camara, telecom) follow this identical structure, varying only `metadata.name`, `spec.prefix`, and `spec.targetRef.name`.

**Prefix naming constraint** (from RESEARCH.md Pitfall 3): lowercase letters a-z, digits 0-9, and underscores only. Must start with letter or digit. No hyphens. Use: `tmf642`, `tmf628`, `tmf621`, `nwdaf`, `camara`, `telecom`.

---

### `gateway/openshift/mcpvs-*.yaml` (config -- MCPVirtualServer CRDs)

**Analog:** None in codebase (new RHCL CRD type). Pattern from RESEARCH.md.

**Pattern from RESEARCH.md Pattern 2** (lines 340-376):
```yaml
apiVersion: mcp.kuadrant.io/v1alpha1
kind: MCPVirtualServer
metadata:
  name: tmf-tools
  namespace: otel25-gateway
spec:
  description: "TMF alarm, performance, and trouble ticket tools for fault prediction"
  tools:
  - tmf642_list_alarms
  - tmf642_get_alarm
  # ... (exact names from MCPServerRegistration discoveredTools)
```

4 MCPVirtualServer files needed: `tmf-tools` (15 TMF tools), `nwdaf-tools` (3 tools), `camara-tools` (2 tools), `infra-tools` (58 MCP-Telecom tools).

**Important:** Tool names must match the exact prefixed names discovered by MCPServerRegistration. Author these AFTER verifying MCPServerRegistration discovery output via `oc get mcpsr -A -o yaml`.

---

### `gateway/openshift/gateway.yaml` and `gateway/openshift/mcp-gateway-extension.yaml` (config)

**Analog:** None in codebase. Patterns from RESEARCH.md.

**Gateway object** (RESEARCH.md Pattern 4, lines 517-531):
```yaml
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: mcp-gateway
  namespace: otel25-gateway
spec:
  gatewayClassName: openshift-default
  listeners:
  - name: mcp
    port: 8080
    protocol: HTTP
    hostname: "mcp.apps.<cluster-domain>"
```

**MCPGatewayExtension** (RESEARCH.md Pattern 4, lines 533-548):
```yaml
apiVersion: mcp.kuadrant.io/v1alpha1
kind: MCPGatewayExtension
metadata:
  name: mcp-gateway-ext
  namespace: otel25-gateway
spec:
  targetRef:
    group: gateway.networking.k8s.io
    kind: Gateway
    name: mcp-gateway
    sectionName: mcp
  httpRouteManagement: Enabled
```

---

### `gateway/openshift/reference-grant.yaml` (config)

**Analog:** None in codebase. Pattern from RESEARCH.md Pitfall 7 (lines 693-708).

```yaml
apiVersion: gateway.networking.k8s.io/v1beta1
kind: ReferenceGrant
metadata:
  name: allow-gateway-to-mcp
  namespace: otel25-mcp
spec:
  from:
  - group: gateway.networking.k8s.io
    kind: HTTPRoute
    namespace: otel25-gateway
  to:
  - group: ""
    kind: Service
```

This lives in `otel25-mcp` (the target namespace), not in `otel25-gateway`.

---

### `gateway/openshift/auth-policy.yaml` (config)

**Analog:** None in codebase. Pattern from RESEARCH.md Pattern 5 (lines 577-608).

```yaml
apiVersion: kuadrant.io/v1
kind: AuthPolicy
metadata:
  name: mcp-auth
  namespace: otel25-gateway
spec:
  targetRef:
    group: gateway.networking.k8s.io
    kind: Gateway
    name: mcp-gateway
    sectionName: mcp
  defaults:
    when:
    - predicate: "!request.path.startsWith('/.well-known')"
  rules:
    authentication:
      jwt-auth:
        jwt:
          issuerUrl: https://<keycloak-host>/realms/mcp
    response:
      unauthenticated:
        body:
          value: '{"error": "Unauthorized", "message": "Authentication required."}'
```

---

### `gateway/openshift/ossm-subscription.yaml` (config -- OLM Subscription)

**Analog:** None in codebase. Pattern from RESEARCH.md Pattern 4 (lines 440-453).

```yaml
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: servicemeshoperator3
  namespace: openshift-operators
spec:
  channel: stable
  installPlanApproval: Automatic
  name: servicemeshoperator3
  source: redhat-operators
  sourceNamespace: openshift-marketplace
```

`mcp-gateway-subscription.yaml` follows the same Subscription pattern (RESEARCH.md lines 493-515):
```yaml
apiVersion: operators.coreos.com/v1alpha1
kind: Subscription
metadata:
  name: mcp-gateway
  namespace: otel25-gateway
spec:
  channel: preview
  name: mcp-gateway
  source: redhat-operators
  sourceNamespace: openshift-marketplace
---
apiVersion: operators.coreos.com/v1
kind: OperatorGroup
metadata:
  name: mcp-gateway-og
  namespace: otel25-gateway
spec:
  targetNamespaces:
  - otel25-gateway
```

---

### `gateway/openshift/istio-cni.yaml` and `gateway/openshift/istio.yaml` (config -- Istio CRDs)

**Analog:** None in codebase. Patterns from RESEARCH.md Pattern 4 (lines 455-488).

**IstioCNI** (lines 455-466):
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: istio-cni
---
apiVersion: sailoperator.io/v1
kind: IstioCNI
metadata:
  name: default
spec:
  namespace: istio-cni
  profile: openshift
```

**Istio** (lines 468-488):
```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: istio-system
  labels:
    istio-discovery: default
---
kind: Istio
apiVersion: sailoperator.io/v1
metadata:
  name: default
  namespace: istio-system
spec:
  namespace: istio-system
  updateStrategy:
    type: InPlace
```

---

## Shared Patterns

### ConfigMap File-Watcher (BACK-03 Compliance)
**Source:** `mcp/tooling/openapi_to_mcp.py` lines 60-120 (SCAFFOLD_TEMPLATE)
**Apply to:** All 5 domain server `server.py` files

The ConfigMap watcher is baked into every generated scaffold by the CLI. It reads the backend URL from a volume-mounted ConfigMap file, polls for mtime changes every 5 seconds, validates URL format (http/https prefix), and mutates the httpx2 client's `base_url` property. No manual implementation needed -- it comes from the CLI.

Key contract: the `backend_env_var` in the allowlist config must match a key in `backends/openshift/configmap-backend-routing.yaml`. Currently defined keys: `TMF642_BASE_URL`, `TMF628_BASE_URL`, `TMF621_BASE_URL`, `CAMARA_BASE_URL`, `CAMARA_RETRIEVAL_BASE_URL`, `NWDAF_BASE_URL`.

### /healthz Endpoint
**Source:** `mcp/mcp-telecom/src/mcp_telecom/server.py` lines 1828-1841
**Apply to:** All 5 domain server `server.py` files (as post-generation hand-curation)

```python
def create_app():
    """Create the ASGI app with custom routes (e.g. /healthz)."""
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    async def healthz(request):
        return JSONResponse({"status": "ok"})

    app = mcp.http_app()
    app.router.routes.append(Route("/healthz", healthz))
    return app
```

The `readinessProbe` in every deployment YAML checks `GET /healthz:8000`. Without this endpoint, pods will fail readiness checks and never become ready.

### OpenShift Deployment + Service
**Source:** `mcp/openshift/mcp-telecom-deployment.yaml` lines 1-61
**Apply to:** All 5 domain server deployment YAMLs in `mcp/openshift/`

Consistent pattern: Deployment + Service in one file, same namespace `otel25-mcp`, same labels structure (`app`, `layer`), same resource requests/limits, same probes, ClusterIP service type, port 8000. Only the name, image reference, and ConfigMap volume mount differ.

### Namespace Naming Convention
**Source:** `backends/openshift/namespace.yaml` + `mcp/openshift/namespace.yaml`
**Apply to:** `gateway/openshift/namespace.yaml`

Pattern: `otel25-<layer>` with `purpose: phase-N-<description>` label.

### Allowlist YAML Structure
**Source:** `mcp/tooling/tests/camara_allowlist.yaml` + `mcp/tooling/allowlist_schema.py`
**Apply to:** All domain server allowlist.yaml files

Four required fields: `server_name`, `spec_path`, `backend_env_var`, `operations[]`. Each operation has `path`, `methods[]`, and optionally `mcp_type` (defaults to `TOOL`).

### Dockerfile Pattern (OpenShift-Compatible)
**Source:** `mcp/mcp-telecom/Dockerfile` lines 1-49
**Apply to:** All 5 domain server Dockerfiles

Key OpenShift compatibility elements that MUST be preserved:
- `python:3.12-slim` base
- uv multi-stage copy from `ghcr.io/astral-sh/uv:latest`
- `chgrp -R 0 /app && chmod -R g=u /app` for arbitrary-UID support
- `UV_CACHE_DIR=/app/.cache/uv` and `PYTHONDONTWRITEBYTECODE=1`
- `USER 1001`
- `EXPOSE 8000`

## No Analog Found

Files with no close match in the codebase (planner should use RESEARCH.md patterns instead):

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `gateway/openshift/ossm-subscription.yaml` | config | -- | No OLM Subscription CRDs exist in codebase; use RESEARCH.md Pattern 4 step 2 |
| `gateway/openshift/istio-cni.yaml` | config | -- | No Istio CRDs exist in codebase; use RESEARCH.md Pattern 4 step 3 |
| `gateway/openshift/istio.yaml` | config | -- | No Istio CRDs exist in codebase; use RESEARCH.md Pattern 4 step 4 |
| `gateway/openshift/cert-manager-subscription.yaml` | config | -- | No cert-manager Subscription; follows same OLM pattern as ossm-subscription |
| `gateway/openshift/mcp-gateway-subscription.yaml` | config | -- | RHCL Operator Subscription + OperatorGroup; use RESEARCH.md Pattern 4 step 6 |
| `gateway/openshift/gateway.yaml` | config | -- | Gateway API Gateway object; use RESEARCH.md Pattern 4 step 7 |
| `gateway/openshift/mcp-gateway-extension.yaml` | config | -- | RHCL MCPGatewayExtension CRD; use RESEARCH.md Pattern 4 step 8 |
| `gateway/openshift/reference-grant.yaml` | config | -- | Gateway API ReferenceGrant; use RESEARCH.md Pitfall 7 |
| `gateway/openshift/mcpsr-tmf642.yaml` | config | -- | RHCL MCPServerRegistration; use RESEARCH.md Pattern 1 (first instance -- siblings copy from it) |
| `gateway/openshift/mcpvs-tmf.yaml` | config | -- | RHCL MCPVirtualServer; use RESEARCH.md Pattern 2 (first instance -- siblings copy from it) |
| `gateway/openshift/auth-policy.yaml` | config | -- | RHCL AuthPolicy; use RESEARCH.md Pattern 5 |
| `scripts/verify-domain-tools.sh` | utility | request-response | No existing verification scripts; use RESEARCH.md Examples 3 and Validation Architecture |
| `scripts/verify-gateway.sh` | utility | request-response | No existing verification scripts; use RESEARCH.md Example 3 |

## Metadata

**Analog search scope:** `mcp/`, `backends/openshift/`, `gateway/` (does not exist yet)
**Files scanned:** 52 source files (excluding .venv, __pycache__)
**Pattern extraction date:** 2026-10-04
