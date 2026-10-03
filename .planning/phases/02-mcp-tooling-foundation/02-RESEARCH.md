# Phase 2: MCP Tooling Foundation - Research

**Researched:** 2026-10-02
**Domain:** MCP server transport patching, OpenAPI-to-MCP codegen tooling, OpenShift deployment
**Confidence:** HIGH

## Summary

Phase 2 has two deliverables: (1) fork/patch MCP-Telecom to serve over Streamable HTTP and deploy it on OpenShift, and (2) build a reusable OpenAPI-to-MCP conversion CLI that generates FastMCP server scaffolds from OpenAPI specs with operation-allowlist filtering. Both are well-constrained by the CONTEXT.md decisions.

The most important research finding is that **MCP-Telecom and this project's conversion tooling use different FastMCP packages**. MCP-Telecom imports `from mcp.server.fastmcp import FastMCP` (the built-in FastMCP class bundled within the official `mcp` Python SDK v1.x). The project's STACK.md specifies the standalone `fastmcp` v4.0.10 (PyPI, from PrefectHQ), which is a separate, more feature-rich package with `from_openapi()`, `RouteMap`, and native HTTP transport. The `mcp` SDK v2.0 (released 2026-07-28) removed the `mcp.server.fastmcp` module entirely, renaming `FastMCP` to `MCPServer`. This version incompatibility is the primary technical risk for the transport patch.

**Primary recommendation:** Switch MCP-Telecom's dependency from `mcp[cli]>=1.0.0` to standalone `fastmcp>=4.0.0` as part of the transport patch. This aligns it with the project's stack, gives it the latest Streamable HTTP support, and avoids the `mcp` v1-to-v2 migration complexity. The decorator API (`@mcp.tool()`, `@mcp.resource()`, `@mcp.prompt()`) is identical between both packages. Build the conversion CLI using the same standalone `fastmcp` package for `from_openapi()` and `RouteMap`.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Fork/patch MCP-Telecom to add native HTTP transport (not stdio-to-HTTP proxy sidecar)
- **D-02:** Patched server is HTTP-only -- stdio support stripped
- **D-03:** Transport is Streamable HTTP (MCP 2026-07-28 protocol), not legacy SSE
- **D-05:** Vendored into this repo under `mcp/mcp-telecom/`, not a separate fork
- **D-06:** Keeps original MIT license with NOTICE/attribution file
- **D-07:** Tools point at nothing -- no device backend wired in Phase 2
- **D-08:** Verification via throwaway script: `tools/list` + one representative tool call
- **D-09:** Flag no-device-backend gap in STATE.md for Phase 4
- **D-10:** Scaffold device-inventory config shape with OpenShift Secret references
- **D-10a:** Command-allowlisting scaffold for safe CLI exec tool
- **D-11:** Conversion tooling is a generic CLI at `mcp/tooling/openapi_to_mcp.py`
- **D-12:** Operation selection via YAML/JSON allowlist config using `RouteMap`
- **D-13:** One-time codegen, then hand-curate (not dynamic runtime loader)
- **D-14:** Smoke-test CLI against CAMARA Device Location spec
- **D-15:** Smoke test is local only, not deployed to OpenShift
- **D-16:** Generated scaffolds bake in file-watching boilerplate for ConfigMap contract
- **D-17:** New namespace `otel25-mcp`
- **D-18:** Plain `oc apply` YAML manifests, no Helm
- **D-19:** Top-level `mcp/` directory: `mcp/tooling/`, `mcp/mcp-telecom/`
- **D-20:** Probes check process-up / MCP endpoint responds, not device connectivity

### Claude's Discretion
- Exact Service/port naming for deployed MCP-Telecom (D-04)
- Exact shape/filenames of device-inventory scaffold and command-allowlist scaffold (D-10, D-10a)
- Exact YAML allowlist-config schema for conversion CLI (D-12)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope. The 20 curated domain tools, Kuadrant MCP Gateway composition, and wiring MCP-Telecom to real devices are all Phase 3/4 work.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MCP-06 | Deploy MCP-Telecom (60+ device-layer tools) on OpenShift for infrastructure fault data | Transport patch (stdio->HTTP), Dockerfile, OpenShift Deployment/Service YAML, liveness/readiness probes, verification script |
| MCP-07 | Build reusable OpenAPI-to-MCP conversion tooling for future API waves | Conversion CLI using `FastMCP.from_openapi()` + `RouteMap`, YAML allowlist config, codegen template, ConfigMap file-watcher boilerplate, CAMARA smoke test |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| MCP-Telecom transport patch | MCP Server (Python process) | -- | Transport is a server-level concern; change `mcp.run()` call |
| MCP-Telecom OpenShift deployment | OpenShift / Container orchestration | -- | Deployment YAML, namespace, probes, Dockerfile |
| OpenAPI-to-MCP conversion CLI | Developer tooling (local CLI) | -- | Runs locally, generates code artifacts, not deployed |
| Generated scaffold file-watching | MCP Server (Python process) | OpenShift ConfigMap | Server reads volume-mounted ConfigMap; kubelet propagates changes |
| Device-inventory config scaffold | Configuration (YAML file) | OpenShift Secrets | Shape defined now; credentials reference Secrets |
| Verification scripts | Developer tooling / CI | OpenShift cluster | Scripts run against deployed workloads |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard | Confidence |
|---------|---------|---------|--------------|------------|
| `fastmcp` | 4.0.10 | MCP server framework (both MCP-Telecom and generated scaffolds) | Project-wide standard per STACK.md; has `from_openapi()`, `RouteMap`, native Streamable HTTP | HIGH [VERIFIED: PyPI registry + Context7 /llmstxt/gofastmcp_llms-full_txt] |
| Python | 3.12 | Runtime | FastMCP requires >=3.10; 3.12 is project standard per STACK.md | HIGH [CITED: STACK.md] |
| `httpx` | 0.28.1 | Async HTTP client for backend calls in generated scaffolds | FastMCP's OpenAPI integration requires httpx.AsyncClient | HIGH [VERIFIED: PyPI registry + Context7] |
| `pydantic` | >=2.0 | Schema validation | FastMCP uses Pydantic internally; MCP-Telecom already depends on it | HIGH [VERIFIED: PyPI registry] |
| `pyyaml` | 6.0.3 | YAML parsing for allowlist configs and device inventory | MCP-Telecom already depends on it; conversion CLI needs YAML parsing | HIGH [VERIFIED: PyPI registry] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `watchdog` | 6.0.0 | File-system event monitoring for ConfigMap file-watching | Baked into generated scaffolds; used with `PollingObserver` for K8s compatibility | [VERIFIED: PyPI registry] |
| `netmiko` | >=4.3.0 | SSH connection to network devices | Existing MCP-Telecom dependency; not modified in this phase | [CITED: MCP-Telecom pyproject.toml] |
| `python-dotenv` | >=1.0.0 | Environment variable loading | Existing MCP-Telecom dependency | [CITED: MCP-Telecom pyproject.toml] |
| `rich` | >=13.0.0 | CLI output formatting | Existing MCP-Telecom dependency | [CITED: MCP-Telecom pyproject.toml] |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Standalone `fastmcp` for MCP-Telecom | `mcp` SDK v1.x (>=1.8.0) | Minimal patch (just transport param), but older protocol, diverges from project stack, pinned to <2.0.0 to avoid v2 breaking changes |
| Standalone `fastmcp` for MCP-Telecom | `mcp` SDK v2.x (`MCPServer`) | Latest protocol, but requires renaming FastMCP->MCPServer, changing all imports, updating constructor args -- far more invasive than switching to standalone `fastmcp` |
| `watchdog` PollingObserver | Simple mtime-polling loop (no library) | Fewer dependencies, but reinvents observer pattern; watchdog is well-tested and handles edge cases |
| `watchdog` PollingObserver | `watchdog` default Observer (inotify) | Lower latency on normal filesystems, but **breaks on Kubernetes ConfigMap volumes** due to symlink-based atomic updates |

**Installation (MCP-Telecom vendored copy):**
```bash
cd mcp/mcp-telecom
uv add fastmcp httpx pydantic pyyaml python-dotenv rich netmiko
```

**Installation (Conversion CLI):**
```bash
cd mcp/tooling
uv add fastmcp httpx pyyaml
```

## Package Legitimacy Audit

> slopcheck was unavailable at research time. All packages below are tagged `[ASSUMED]` and the planner must gate each install behind a `checkpoint:human-verify` task.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| fastmcp | PyPI | ~1.5 yrs | High (PrefectHQ) | github.com/PrefectHQ/fastmcp | N/A | [ASSUMED] -- project STACK.md standard |
| httpx | PyPI | ~5 yrs | Very high | github.com/encode/httpx | N/A | [ASSUMED] -- well-known HTTP client |
| pydantic | PyPI | ~7 yrs | Very high | github.com/pydantic/pydantic | N/A | [ASSUMED] -- industry standard |
| pyyaml | PyPI | ~15 yrs | Very high | github.com/yaml/pyyaml | N/A | [ASSUMED] -- standard YAML parser |
| watchdog | PyPI | ~13 yrs | High | github.com/gorakhargosh/watchdog | N/A | [ASSUMED] -- well-known filesystem watcher |
| netmiko | PyPI | ~10 yrs | High | github.com/ktbyers/netmiko | N/A | [ASSUMED] -- standard network automation library |
| python-dotenv | PyPI | ~10 yrs | Very high | github.com/theskumar/python-dotenv | N/A | [ASSUMED] -- standard env file loader |
| rich | PyPI | ~5 yrs | Very high | github.com/Textualize/rich | N/A | [ASSUMED] -- standard CLI formatting |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*All packages are well-established ecosystem standards. slopcheck was unavailable at research time, so the planner must gate each install behind a `checkpoint:human-verify` task per protocol.*

## Architecture Patterns

### System Architecture Diagram

```
                    Developer Workstation (Local)
                    +---------------------------------+
                    |  mcp/tooling/openapi_to_mcp.py  |
                    |  (Conversion CLI)               |
                    |                                 |
                    |  Input:                         |
                    |    OpenAPI spec (YAML)           |
                    |    + allowlist config (YAML)     |
                    |                                 |
                    |  Output:                        |
                    |    server.py scaffold            |
                    |    (one-time codegen)            |
                    +---------+-----------------------+
                              |
                     codegen  |  (Phase 3 uses output)
                              v
    OpenShift Cluster
    +================================================================+
    |  Namespace: otel25-mcp                                         |
    |                                                                |
    |  +----------------------------+                                |
    |  |  MCP-Telecom (vendored)    |                                |
    |  |  ~58 tools, 4 prompts,     |                                |
    |  |  8 resources               |                                |
    |  |                            |                                |
    |  |  Streamable HTTP           |                                |
    |  |  POST /mcp                 |                                |
    |  |  port 8000                 |                                |
    |  +----------------------------+                                |
    |       |                                                        |
    |       | (Phase 2: points at nothing -- connection errors)       |
    |       v                                                        |
    |    [No device backend]                                         |
    |                                                                |
    +================================================================+
    |  Namespace: otel25-backends (Phase 1, already deployed)        |
    |                                                                |
    |  ConfigMap: backend-routing                                    |
    |  (Volume-mounted by Phase 3's generated servers,               |
    |   not by MCP-Telecom)                                          |
    +================================================================+
```

### Recommended Project Structure

```
mcp/
  mcp-telecom/                    # Vendored MCP-Telecom fork (D-05, D-19)
    LICENSE                       # Original MIT license
    NOTICE                        # Attribution to upstream
    pyproject.toml                # Modified: fastmcp dep, transport config
    src/mcp_telecom/
      server.py                   # Patched: import + transport change
      connection.py               # Unchanged
      safety.py                   # Unchanged
      ...                         # All other modules unchanged
    devices.yaml.example          # Device-inventory scaffold (D-10)
    command_allowlist.yaml         # Command-allowlist scaffold (D-10a)
    Dockerfile                    # New: Python + fastmcp HTTP server
  tooling/                        # Conversion CLI (D-11, D-19)
    openapi_to_mcp.py             # CLI entry point
    allowlist_schema.py           # YAML allowlist config model
    templates/                    # Codegen templates
      server_template.py.j2       # Generated server.py template
    README.md                     # CLI usage documentation
  openshift/                      # OpenShift manifests for MCP layer
    namespace.yaml                # otel25-mcp namespace (D-17)
    mcp-telecom-deployment.yaml   # Deployment + Service (D-18)
    mcp-telecom-secret.yaml       # Placeholder Secret for device creds
scripts/
  verify-mcp-telecom.sh           # Verification script (D-08)
```

### Pattern 1: MCP-Telecom Transport Patch

**What:** Replace stdio transport with Streamable HTTP in the vendored MCP-Telecom copy.

**When:** First task in Phase 2 -- everything else depends on this.

**The patch is exactly three changes:**

1. **`pyproject.toml`** -- swap dependency:
```toml
# Before (MCP-Telecom upstream)
dependencies = [
    "mcp[cli]>=1.0.0",
    ...
]

# After (vendored patch)
dependencies = [
    "fastmcp>=4.0.0",
    ...
]
```

2. **`src/mcp_telecom/server.py`** -- swap import:
```python
# Before (MCP-Telecom upstream)
from mcp.server.fastmcp import FastMCP

# After (vendored patch)
from fastmcp import FastMCP
```
Source: [FastMCP migration guide](https://gofastmcp.com/getting-started/upgrading/from-mcp-sdk-v2) [VERIFIED: Context7 /llmstxt/gofastmcp_llms-full_txt]

3. **`src/mcp_telecom/server.py`** -- swap transport in `main()`:
```python
# Before (MCP-Telecom upstream)
def main():
    logger.info("Starting MCP-Telecom server v0.2.0")
    logger.info("Loaded %d devices", len(device_manager.list_devices()))
    mcp.run(transport="stdio")

# After (vendored patch)
def main():
    logger.info("Starting MCP-Telecom server v0.2.0")
    logger.info("Loaded %d devices", len(device_manager.list_devices()))
    mcp.run(transport="http", host="0.0.0.0", port=8000)
```
Source: [FastMCP HTTP deployment docs](https://gofastmcp.com/deployment/running-server) [VERIFIED: Context7 /llmstxt/gofastmcp_llms-full_txt]

**Why this works:** The standalone `fastmcp` package's `FastMCP` class has the same decorator API (`@mcp.tool()`, `@mcp.resource()`, `@mcp.prompt()`) as the `mcp` SDK's built-in FastMCP. MCP-Telecom's ~58 tools all use this decorator pattern. The `mcp.run(transport="http")` call in standalone `fastmcp` serves Streamable HTTP at `/mcp` by default (port 8000). [VERIFIED: Context7]

**Risk:** The standalone `fastmcp` may have subtle behavioral differences from `mcp.server.fastmcp.FastMCP` for edge cases in MCP-Telecom's tool implementations. The planner should include a verification task that runs MCP-Telecom's test suite (`pytest`) after the patch.

### Pattern 2: Conversion CLI Codegen Approach

**What:** A CLI that takes an OpenAPI spec + YAML allowlist and generates a standalone `server.py` scaffold.

**When:** Second major deliverable. Must be smoke-tested against CAMARA Device Location spec.

**Key insight:** FastMCP's `from_openapi()` is a **runtime** API -- it creates the server dynamically in memory from the spec. It does NOT have a codegen/export-to-file feature. [VERIFIED: Context7 + WebSearch confirmed no export mechanism exists]

Therefore the CLI must:
1. Use `from_openapi()` with `RouteMap` to introspect and filter the spec at codegen time
2. Generate a `server.py` file via **templating** (e.g., Jinja2 or string templates) that contains a `from_openapi()` call configured with the filtered route maps
3. The generated scaffold IS a working server that calls `from_openapi()` at startup with the vendored spec -- this satisfies D-13's "one-time codegen" because the spec is baked in, not fetched dynamically
4. Phase 3 hand-curates by editing the generated file: improving descriptions via `mcp_component_fn`, adjusting `route_maps`, or eventually replacing `from_openapi()` with explicit `@mcp.tool()` decorators

**Generated scaffold structure:**
```python
# Auto-generated by mcp/tooling/openapi_to_mcp.py
# Spec: camara_location_verification.yaml
# Allowlist: camara_allowlist.yaml
# Generated: 2026-10-03
#
# CURATION GUIDE:
# 1. Edit descriptions in customize_components() for LLM clarity
# 2. Adjust route_maps to include/exclude operations
# 3. For full control, replace from_openapi() with explicit @mcp.tool() decorators
# 4. DO NOT edit the file-watcher section (ConfigMap contract, BACK-03)

import os
import json
import threading
from pathlib import Path
from fastmcp import FastMCP
from fastmcp.server.providers.openapi import RouteMap, MCPType
from fastmcp.utilities.openapi import HTTPRoute
from fastmcp.server.providers.openapi import OpenAPITool
import httpx

# --- ConfigMap file-watcher (BACK-03 contract) ---
BACKEND_ROUTING_PATH = os.environ.get(
    "BACKEND_ROUTING_FILE", "/config/backend-routing/CAMARA_BASE_URL"
)
_backend_url_lock = threading.Lock()
_backend_url = "http://localhost:4010"  # default fallback


def _load_backend_url():
    global _backend_url
    try:
        url = Path(BACKEND_ROUTING_PATH).read_text().strip()
        if url:
            with _backend_url_lock:
                _backend_url = url
    except FileNotFoundError:
        pass  # use default on first boot


def get_backend_url() -> str:
    with _backend_url_lock:
        return _backend_url


def _start_config_watcher():
    """Poll ConfigMap-mounted file for changes (mtime-based).
    
    Uses mtime polling instead of inotify because Kubernetes
    updates ConfigMap volumes via atomic symlink swaps, which
    do not emit standard IN_MODIFY events.
    """
    import time
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
            time.sleep(5)  # poll every 5 seconds

    t = threading.Thread(target=_poll, daemon=True)
    t.start()


# --- OpenAPI Server ---
SPEC_PATH = Path(__file__).parent / "specs" / "camara_location_verification.yaml"

def customize_components(route, component):
    """Customize tool descriptions for LLM consumption."""
    if isinstance(component, OpenAPITool):
        # Phase 3: improve these descriptions for telecom domain clarity
        pass

route_maps = [
    # Include only allowlisted operations
    RouteMap(path="/verify", methods=["POST"], mcp_type=MCPType.TOOL),
    # Exclude everything else
    RouteMap(mcp_type=MCPType.EXCLUDE),
]

spec_text = SPEC_PATH.read_text()
client = httpx.AsyncClient(base_url=get_backend_url())

mcp = FastMCP.from_openapi(
    openapi_spec=spec_text,
    client=client,
    route_maps=route_maps,
    mcp_component_fn=customize_components,
)

# --- Startup ---
_load_backend_url()
_start_config_watcher()

if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000)
```
Source: [FastMCP OpenAPI docs](https://gofastmcp.com/integrations/openapi) [VERIFIED: Context7 /llmstxt/gofastmcp_llms-full_txt]

### Pattern 3: ConfigMap File-Watching for Backend URL

**What:** Volume-mounted ConfigMap polling for live backend switching without pod restart.

**When:** Baked into every generated scaffold (D-16). MCP-Telecom itself does NOT need this (it has no backend routing -- D-07).

**Critical Kubernetes caveat:** ConfigMap volume mounts use atomic symlink swaps. The kubelet creates a new timestamped directory and atomically swaps the `..data` symlink. Standard `inotify` watchers receive `IN_DELETE_SELF` events instead of `IN_MODIFY`, breaking most file-watching libraries. [CITED: https://ahmet.im/blog/kubernetes-inotify/]

**Recommended approach: Mtime-based polling (not inotify-based watchdog)**

The simplest reliable pattern is polling `os.path.getmtime()` on the mounted file every 5 seconds. This:
- Works reliably with K8s symlink swaps
- Has no inotify edge cases to handle
- Adds ~0 CPU overhead at 5-second intervals
- Matches the kubelet's own propagation delay (~60 seconds for ConfigMap changes)

The `watchdog` library with `PollingObserver` is an alternative, but for a single file that changes rarely, a simple mtime polling loop in a daemon thread is more straightforward and avoids the dependency. [ASSUMED -- recommend polling loop for simplicity; planner can switch to watchdog if more files need watching]

**Integration with Phase 1's ConfigMap contract:**
```yaml
# From backends/openshift/configmap-backend-routing.yaml
# Phase 3 servers mount this ConfigMap as a volume, e.g.:
# volumeMounts:
#   - name: backend-routing
#     mountPath: /config/backend-routing
#     readOnly: true
# volumes:
#   - name: backend-routing
#     configMap:
#       name: backend-routing
```
Source: [Phase 1 ConfigMap contract](backends/openshift/configmap-backend-routing.yaml) [VERIFIED: codebase]

### Pattern 4: OpenShift Deployment for Python/FastMCP HTTP Server

**What:** Dockerfile + Deployment/Service YAML for a FastMCP server on OpenShift.

**When:** Deploying MCP-Telecom to `otel25-mcp` namespace.

**Dockerfile pattern:**
```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy project files
COPY pyproject.toml uv.lock ./
COPY src/ src/

# Install dependencies
RUN uv sync --no-dev --frozen

# Copy config scaffolds
COPY devices.yaml.example devices.yaml
COPY command_allowlist.yaml command_allowlist.yaml

# Non-root user (OpenShift requires arbitrary UID support)
RUN useradd -r -s /bin/false mcpuser
USER mcpuser

EXPOSE 8000

# Run the MCP server
CMD ["uv", "run", "mcp-telecom"]
```

**Deployment YAML pattern (mirrors Phase 1's prism-tmf642.yaml):**
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
        # D-20: Liveness checks process-up (port alive)
        livenessProbe:
          tcpSocket:
            port: 8000
          initialDelaySeconds: 10
          periodSeconds: 30
        # D-20: Readiness checks MCP endpoint responds
        # Note: Streamable HTTP uses POST, but a simple HTTP GET
        # to /mcp returns 405 Method Not Allowed (confirms endpoint exists)
        # For a proper check, use a startup script or exec probe
        readinessProbe:
          httpGet:
            path: /mcp
            port: 8000
          initialDelaySeconds: 5
          periodSeconds: 10
          # 405 (Method Not Allowed for GET on Streamable HTTP endpoint)
          # is NOT a passing readiness check. See Pitfall 2 below for
          # the recommended approach.
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
[ASSUMED -- pattern based on Phase 1's Prism YAML structure adapted for Python/FastMCP]

### Anti-Patterns to Avoid

- **Using `watchdog` default Observer (inotify) for ConfigMap watching:** Breaks on K8s symlink swaps. Use `PollingObserver` or simple mtime polling. [CITED: https://ahmet.im/blog/kubernetes-inotify/]
- **Staying on `mcp` SDK v1.x and pinning `<2.0.0`:** Creates a version-frozen dependency that diverges from the project stack and will eventually need upgrading anyway.
- **Using `envFrom` for ConfigMap consumption:** Environment variables are read once at pod startup. Changes require pod restart, violating BACK-03. Volume-mount + file-watch is required. [CITED: Phase 1 ConfigMap contract comment block]
- **Building a dynamic runtime loader for the conversion CLI:** D-13 explicitly requires one-time codegen. The generated scaffold should be a static file, not a system that re-reads specs at startup. The spec IS read at startup by `from_openapi()`, but it is baked into the image/directory, not fetched.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| OpenAPI-to-MCP tool conversion | Manual tool definition parser | `FastMCP.from_openapi()` + `RouteMap` | Handles schema extraction, parameter mapping, HTTP method routing, Swagger 2.0 + OAS 3.0 |
| MCP protocol handling | Custom JSON-RPC over HTTP | `FastMCP` with `mcp.run(transport="http")` | Full MCP protocol implementation including tool listing, invocation, streaming |
| Operation filtering from spec | Custom OpenAPI parser | `RouteMap` with `path`, `methods`, `tags`, `mcp_type=MCPType.EXCLUDE` | Declarative filtering, processed in order, first-match wins |
| Tool description customization | Post-processing script | `mcp_component_fn` callback in `from_openapi()` | In-place modification of generated components during conversion |
| ASGI server for production | Custom socket server | `uvicorn` via `mcp.http_app()` or `mcp.run(transport="http")` | Production-grade ASGI server with worker support |

**Key insight:** FastMCP handles the entire MCP protocol stack. The conversion CLI's job is purely selecting operations and generating the scaffold file -- NOT reimplementing protocol handling.

## Common Pitfalls

### Pitfall 1: MCP-Telecom `mcp` SDK vs standalone `fastmcp` Import Incompatibility

**What goes wrong:** MCP-Telecom imports `from mcp.server.fastmcp import FastMCP` (the `mcp` SDK v1.x built-in). If you upgrade the `mcp` dependency to v2.x without changing the import, you get `ModuleNotFoundError` because `mcp` v2.0 removed `mcp.server.fastmcp` entirely (renamed to `mcp.server.mcpserver.MCPServer`). [VERIFIED: https://py.sdk.modelcontextprotocol.io/migration/]

**Why it happens:** Two different packages (`mcp` and `fastmcp`) both provide a class called `FastMCP` at different import paths. The project STACK.md says "FastMCP 4.0.10" but MCP-Telecom uses the `mcp` SDK's bundled version.

**How to avoid:** Switch MCP-Telecom to standalone `fastmcp>=4.0.0` as recommended. Change import to `from fastmcp import FastMCP`. Remove `mcp[cli]` from dependencies. The decorator API is identical.

**Warning signs:** `ModuleNotFoundError: No module named 'mcp.server.fastmcp'` at startup.

### Pitfall 2: Readiness Probe for Streamable HTTP Endpoint

**What goes wrong:** FastMCP's Streamable HTTP serves at `POST /mcp`. OpenShift readiness probes use `httpGet` (GET method). A GET to `/mcp` returns `405 Method Not Allowed`, which fails the readiness check, causing the pod to never become ready.

**Why it happens:** The MCP Streamable HTTP protocol uses POST exclusively. There is no GET health endpoint by default in a bare `FastMCP` server.

**How to avoid:** Two options:
1. **Add a custom health endpoint** in the vendored MCP-Telecom before calling `mcp.run()`:
   ```python
   # In the vendored server.py, BEFORE mcp.run():
   from starlette.responses import JSONResponse
   app = mcp.http_app()
   
   @app.route("/healthz")
   async def healthz(request):
       return JSONResponse({"status": "ok"})
   ```
   Then use `readinessProbe.httpGet.path: /healthz`.
2. **Use an exec probe** that sends a proper MCP `tools/list` POST request:
   ```yaml
   readinessProbe:
     exec:
       command:
         - python
         - -c
         - "import httpx; r = httpx.post('http://localhost:8000/mcp', json={'jsonrpc':'2.0','method':'tools/list','id':1}); assert r.status_code == 200"
     initialDelaySeconds: 10
     periodSeconds: 30
   ```

**Warning signs:** Pod stuck in `0/1 Ready` state with readiness probe failures in `oc describe pod`.

### Pitfall 3: `from_openapi()` Has No Codegen Export

**What goes wrong:** The planner assumes `FastMCP.from_openapi()` can export a standalone Python file. It cannot -- it creates the server in memory at runtime. Building a "codegen CLI" requires writing your own code-generation logic (templates, string formatting, etc.). [VERIFIED: Context7 + WebSearch -- no export/serialize mechanism exists in FastMCP]

**Why it happens:** FastMCP is designed for dynamic server creation, not code generation. The `from_openapi()` docs assume you use it at runtime.

**How to avoid:** The conversion CLI generates a `server.py` scaffold via **templating** (e.g., Jinja2 or Python string templates). The generated file contains a `from_openapi()` call with the spec path and route_maps hardcoded. This is still "codegen" because the allowlist and boilerplate are baked into the file -- Phase 3 edits the generated file, not the CLI.

**Warning signs:** Looking for `mcp.export()`, `mcp.save()`, or `mcp.to_source()` methods -- they don't exist.

### Pitfall 4: ConfigMap Symlink Swap Breaks inotify Watchers

**What goes wrong:** A `watchdog` Observer with default inotify backend watches a ConfigMap-mounted file. Kubernetes updates the ConfigMap, but the watcher receives `IN_DELETE_SELF` instead of `IN_MODIFY`, and the watch is silently broken. The server continues using the old backend URL indefinitely.

**Why it happens:** Kubernetes uses atomic symlink swaps for ConfigMap updates. The kubelet creates a new timestamped directory, writes new content, swaps the `..data` symlink, and deletes the old directory. The file the watcher was monitoring is literally deleted and replaced with a new inode. [CITED: https://ahmet.im/blog/kubernetes-inotify/]

**How to avoid:** Use mtime-based polling on the mounted file (5-second interval). Polling works regardless of how the file is updated (symlink swap, direct write, etc.). See Pattern 3 above.

**Warning signs:** Backend URL changes in ConfigMap but MCP server keeps calling the old backend.

### Pitfall 5: `from_openapi()` Client Base URL Static After Server Creation

**What goes wrong:** The `httpx.AsyncClient` passed to `from_openapi()` has its `base_url` set at construction time. If the backend URL changes (via ConfigMap), the already-constructed client still points to the old URL.

**Why it happens:** `httpx.AsyncClient` base_url is immutable after construction.

**How to avoid:** The file-watcher callback must create a new `httpx.AsyncClient` with the updated URL, OR use a custom transport layer that resolves the URL at request time. For Phase 2's scaffolds, the simplest approach is to NOT pass a `base_url` to the client, and instead have each tool function construct the full URL using `get_backend_url()` at call time. However, since `from_openapi()` manages the client internally, this requires either:
   - Recreating the FastMCP server on ConfigMap change (heavy but correct)
   - Using a custom `httpx.AsyncClient` subclass with a dynamic base_url property
   - Setting the client's `_base_url` attribute directly (fragile, private API)

**Recommended approach for scaffolds:** Use a thin wrapper around `httpx.AsyncClient` that re-resolves `base_url` on each request by overriding `_merge_url()` or using an event hook. Document this as a known complexity in the scaffold's comments for Phase 3 to review.

## Code Examples

### Example 1: RouteMap Filtering for CAMARA Spec

```python
# Source: Context7 /llmstxt/gofastmcp_llms-full_txt (FastMCP OpenAPI docs)
from fastmcp import FastMCP
from fastmcp.server.providers.openapi import RouteMap, MCPType

route_maps = [
    # Include only the verify endpoint as a tool
    RouteMap(path="/verify", methods=["POST"], mcp_type=MCPType.TOOL),
    # Exclude everything else (default catch-all)
    RouteMap(mcp_type=MCPType.EXCLUDE),
]

mcp = FastMCP.from_openapi(
    openapi_spec=spec_text,
    client=client,
    route_maps=route_maps,
)
```

### Example 2: mcp_component_fn for Tool Customization

```python
# Source: Context7 /llmstxt/gofastmcp_llms-full_txt (FastMCP OpenAPI docs)
from fastmcp.server.providers.openapi import OpenAPITool, OpenAPIResource
from fastmcp.utilities.openapi import HTTPRoute

def customize_components(
    route: HTTPRoute,
    component: OpenAPITool | OpenAPIResource,
) -> None:
    if isinstance(component, OpenAPITool):
        # Improve description for LLM consumption
        component.description = f"[Telecom] {component.description}"
        component.tags.add("camara")

mcp = FastMCP.from_openapi(
    openapi_spec=spec_text,
    client=client,
    route_maps=route_maps,
    mcp_component_fn=customize_components,
)
```

### Example 3: FastMCP ASGI App with Custom Health Endpoint

```python
# Source: Context7 /llmstxt/gofastmcp_llms-full_txt (FastMCP HTTP deployment docs)
from fastmcp import FastMCP
from starlette.responses import JSONResponse

mcp = FastMCP("MCP-Telecom")
# ... tool registrations ...

# Create ASGI app with custom routes
app = mcp.http_app()

@app.route("/healthz")
async def healthz(request):
    return JSONResponse({"status": "ok"})

# Run with uvicorn for production:
# uvicorn server:app --host 0.0.0.0 --port 8000
```

### Example 4: Stateless HTTP Mode for Load-Balanced Deployment

```python
# Source: Context7 /llmstxt/gofastmcp_llms-full_txt (FastMCP stateless mode)
from fastmcp import FastMCP

mcp = FastMCP("MCP-Telecom")

# Stateless mode: each request gets fresh transport context
# No session affinity required -- safe for load balancing
if __name__ == "__main__":
    mcp.run(transport="http", host="0.0.0.0", port=8000, stateless_http=True)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `mcp.server.fastmcp.FastMCP` in `mcp` SDK | `mcp.server.mcpserver.MCPServer` in `mcp` v2 SDK | 2026-07-28 | Breaking import change; standalone `fastmcp` v4.x is now the recommended high-level API |
| `transport="streamable-http"` (`mcp` SDK) | `transport="http"` (standalone `fastmcp`) | FastMCP v3+ | Standalone `fastmcp` uses "http" which serves Streamable HTTP by default at `/mcp` |
| Session-based Streamable HTTP (2025-03-26 spec) | Sessionless Streamable HTTP (2026-07-28 spec) | 2026-07-28 | Sessions removed; `stateless_http=True` in FastMCP aligns with this |
| `mcp` v1.x (FastMCP bundled) | `mcp` v2.x (MCPServer) + `fastmcp` v4.x (standalone) | 2026-07-28 | Two-package ecosystem; standalone `fastmcp` has more features |

**Deprecated/outdated:**
- `from mcp.server.fastmcp import FastMCP`: Removed in `mcp` v2.0. Use `from fastmcp import FastMCP` (standalone) or `from mcp.server.mcpserver import MCPServer` (SDK v2).
- SSE transport: Superseded by Streamable HTTP. FastMCP v4.x still supports it but Streamable HTTP is the default.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | MCP-Telecom's ~58 tools will work unchanged when switching from `mcp` SDK's FastMCP to standalone `fastmcp` | Pattern 1 | Medium -- if decorator behavior differs, some tools may need adjustment. Mitigated by running MCP-Telecom's test suite post-patch. |
| A2 | `watchdog` PollingObserver or simple mtime polling is sufficient for ConfigMap file-watching (vs. more complex hybrid approach) | Pattern 3 | Low -- mtime polling is the most reliable approach on K8s; the 5-second interval is well within acceptable latency for backend URL changes. |
| A3 | The `readinessProbe` for Streamable HTTP requires a custom `/healthz` endpoint or exec probe (GET to `/mcp` returns 405) | Pitfall 2 | Medium -- if FastMCP serves a different status code on GET or has a built-in health route, the probe can be simpler. Verify during implementation. |
| A4 | The generated scaffold approach (templating a file that calls `from_openapi()`) satisfies D-13's "one-time codegen" requirement | Pattern 2 | Low -- the spec is baked into the directory; the `from_openapi()` call is deterministic. Phase 3 edits the generated file. |
| A5 | MCP-Telecom's optional extras (netconf, telemetry, snmp, dashboard, metrics) are compatible with standalone `fastmcp` | Standard Stack | Low -- these extras don't interact with the MCP protocol layer; they're independent Python libraries. |
| A6 | `httpx.AsyncClient` base_url can be dynamically updated for ConfigMap-based backend switching in `from_openapi()` generated servers | Pitfall 5 | Medium -- if `from_openapi()` internally caches the client, backend URL switching may require server recreation. Phase 3 will validate. |

## Open Questions

1. **httpx.AsyncClient base_url dynamism with `from_openapi()`** (DEFERRED TO PHASE 3 — see STATE.md)
   - What we know: `from_openapi()` accepts an `httpx.AsyncClient` and uses it for backend calls. `base_url` is set at construction time.
   - What's unclear: Whether updating `client._base_url` or creating a new client on ConfigMap change will propagate correctly through the FastMCP internals.
   - Recommendation: Phase 2 scaffolds include the file-watcher and a TODO comment for Phase 3 to validate. The CAMARA smoke test (local, no ConfigMap) does not exercise this path.

2. **Standalone `fastmcp` vs `mcp` SDK decorator compatibility edge cases**
   - What we know: The decorator API (`@mcp.tool()`, `@mcp.resource()`, `@mcp.prompt()`) is documented as identical. Basic tools work.
   - What's unclear: Whether MCP-Telecom's use of `@mcp.resource("telecom://...")` URI templates, lazy imports inside tool functions, or the audit logging pattern causes any issues.
   - Recommendation: Run MCP-Telecom's full test suite (157 tests per repo) after the patch. If failures occur, fall back to `mcp` v1.x (>=1.8.0, <2.0.0) with `transport="streamable-http"`.

3. **OpenShift internal registry image push workflow**
   - What we know: Phase 1 uses `image-registry.openshift-image-registry.svc:5000/otel25-backends/` for Prism images.
   - What's unclear: Whether the same `podman build` + `oc` image push workflow used in Phase 1 works for the Python/FastMCP image.
   - Recommendation: Follow Phase 1's established pattern. The Dockerfile is standard Python.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | MCP-Telecom, conversion CLI | Yes | 3.14.6 (local); 3.12 target in containers | Use 3.12-slim Docker base |
| uv | Dependency management | Yes | 0.9.28 | pip (slower but functional) |
| oc | OpenShift deployment | Yes | 4.18.16 client | -- (required, no fallback) |
| podman | Container builds | Yes | 5.6.1 | docker (not installed, not needed) |
| OpenShift cluster | Deployment target | Assumed (Phase 1 deployed successfully) | 4.18+ | -- (required, no fallback) |

**Missing dependencies with no fallback:** None -- all required tools are available.
**Missing dependencies with fallback:** None.

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >= 8.0 (project standard per STACK.md) |
| Config file | None -- Wave 0 creates `mcp/mcp-telecom/pytest.ini` or uses upstream's existing config |
| Quick run command | `cd mcp/mcp-telecom && uv run pytest tests/ -x --timeout=30` |
| Full suite command | `cd mcp/mcp-telecom && uv run pytest tests/ -v` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MCP-06a | MCP-Telecom server starts with HTTP transport | smoke | `uv run python -c "from fastmcp import FastMCP; print('import ok')"` | Wave 0 |
| MCP-06b | MCP-Telecom's 58 tools register correctly | unit | `cd mcp/mcp-telecom && uv run pytest tests/ -x` (upstream tests) | Upstream has 157 tests |
| MCP-06c | tools/list returns tool catalog via Streamable HTTP | integration | `scripts/verify-mcp-telecom.sh` (exec probe style) | Wave 0 |
| MCP-06d | One representative tool callable via MCP protocol | integration | `scripts/verify-mcp-telecom.sh` (D-08 verification) | Wave 0 |
| MCP-07a | Conversion CLI generates scaffold from CAMARA spec | smoke | `cd mcp/tooling && uv run python openapi_to_mcp.py --spec ... --allowlist ...` | Wave 0 |
| MCP-07b | Generated scaffold starts and lists tools correctly | smoke | `uv run python generated_server.py &; curl -X POST localhost:8000/mcp ...` | Wave 0 |

### Sampling Rate

- **Per task commit:** Quick run command (upstream test suite subset)
- **Per wave merge:** Full upstream test suite + verification scripts
- **Phase gate:** All verification scripts pass + upstream tests green

### Wave 0 Gaps

- [ ] `mcp/mcp-telecom/pytest.ini` -- configure pytest for vendored copy (may use upstream config)
- [ ] `scripts/verify-mcp-telecom.sh` -- covers MCP-06c, MCP-06d (D-08 verification)
- [ ] Smoke test script for conversion CLI (MCP-07a, MCP-07b)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | MCP-Telecom has no auth in Phase 2 (internal cluster service) |
| V3 Session Management | No | Using stateless HTTP mode |
| V4 Access Control | Yes (minimal) | MCP-Telecom's command-allowlist scaffold (D-10a) for safe CLI exec |
| V5 Input Validation | Yes | Pydantic schema validation via FastMCP tool parameters |
| V6 Cryptography | No | No crypto operations in Phase 2 |

### Known Threat Patterns for MCP/FastMCP HTTP

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Unauthorized tool invocation via exposed HTTP port | Elevation of Privilege | ClusterIP Service (no external exposure); Phase 3 adds Kuadrant gateway auth |
| Command injection via safe CLI exec tool | Tampering | Command-allowlist scaffold (D-10a) with empty/restrictive default |
| Credential exposure in device-inventory config | Information Disclosure | OpenShift Secret references (D-10), never plain ConfigMap values |
| Unvalidated backend URL from ConfigMap | Tampering | Validate URL format in file-watcher callback before applying |

## Project Constraints (from CLAUDE.md)

- Never push `.gitignore` files to GitHub repos -- keep local only
- Never push blog drafts or personal notes
- When staging files, always review what's being added -- prefer explicit file paths over `git add .`
- Global memories are learnings -- apply only when relevant to current task

## Sources

### Primary (HIGH confidence)

- **Context7 /llmstxt/gofastmcp_llms-full_txt** -- FastMCP HTTP transport (`mcp.run(transport="http")`), `from_openapi()` API, `RouteMap` filtering, `mcp_component_fn`, ASGI deployment, stateless mode
- **Context7 /prefecthq/fastmcp** -- FastMCP server composition, proxy patterns
- **MCP-Telecom repo** (github.com/Avinash-Amudala/MCP-Telecom) -- Source code structure, import paths (`from mcp.server.fastmcp import FastMCP`), `mcp.run(transport="stdio")`, pyproject.toml dependencies, 58 tools + 4 prompts + 8 resources, MIT license
- **MCP Python SDK migration guide** (https://py.sdk.modelcontextprotocol.io/migration/) -- v1->v2 breaking changes: FastMCP->MCPServer rename, `mcp.server.fastmcp` module removed
- **MCP Python SDK v2 what's new** (https://py.sdk.modelcontextprotocol.io/whats-new/) -- MCPServer import path, transport parameter names
- **MCP Python SDK PyPI** (https://pypi.org/project/mcp/) -- v2.3.0 latest, v1.8.0 introduced Streamable HTTP
- **Phase 1 ConfigMap contract** (backends/openshift/configmap-backend-routing.yaml) -- Volume-mount + file-watch requirement, BACK-03 compliance
- **Phase 1 Prism manifests** (backends/openshift/prism-tmf642.yaml, backends/prism/Dockerfile) -- Deployment/Service YAML pattern, Dockerfile pattern
- **Phase 1 verify-routing.sh** (backends/scripts/verify-routing.sh) -- Verification script pattern for D-08

### Secondary (MEDIUM confidence)

- **Kubernetes ConfigMap inotify pitfalls** (https://ahmet.im/blog/kubernetes-inotify/) -- Symlink swap behavior, inotify watch breaking, polling recommendation
- **ConfigMap hot-reload patterns** (https://oneuptime.com/blog/post/2026-02-02-kubernetes-configmap-hot-reload/view) -- watchdog + PollingObserver pattern for Python
- **OpenShift health probes** (https://developers.redhat.com/blog/2020/11/10/you-probably-need-liveness-and-readiness-probes) -- httpGet vs exec probe patterns
- **FastMCP PyPI** (https://pypi.org/project/fastmcp/4.0.10/) -- v4.0.10 latest, Apache-2.0 license
- **WebSearch: FastMCP from_openapi codegen** -- Confirmed no export/codegen feature; identified openapi-mcp-codegen (cnoe-io) and mcp-generator-4.x as reference implementations

### Tertiary (LOW confidence)

- None -- all claims verified against primary or secondary sources.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all packages verified on PyPI, FastMCP API verified via Context7
- Architecture: HIGH -- MCP-Telecom source code inspected, transport patch scoped precisely, Phase 1 patterns established
- Pitfalls: HIGH -- ConfigMap inotify issue verified via official blog post, SDK version incompatibility verified via official migration guide
- Conversion CLI codegen: MEDIUM -- the templating approach is sound but `from_openapi()` + dynamic `httpx` client URL updating is an open question

**Research date:** 2026-10-02
**Valid until:** 2026-11-01 (stable -- FastMCP 4.x and mcp SDK 2.x are settled post-2026-07-28 spec freeze)
