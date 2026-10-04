# Phase 3: MCP Domain Servers and Gateway - Research

**Researched:** 2026-10-04
**Domain:** RHCL MCP Gateway (OpenShift Operator), domain MCP server generation, FastMCP OpenAPI integration, Istio/OSSM data plane
**Confidence:** HIGH (gateway docs verified), MEDIUM (some RHCL edge cases unverifiable without cluster access)

## Summary

Phase 3 has three major workstreams: (1) generate and deploy 5 domain MCP servers (20 tools total) using Phase 2's proven conversion CLI, (2) install Red Hat Connectivity Link's MCP Gateway on OpenShift with its prerequisite infrastructure (OSSM 3.3+, cert-manager 1.19, Gateway API), and (3) register all 6 MCP backends behind the gateway with per-domain Virtual MCP Servers and authentication.

The highest-impact research finding is the **resolution of the Phase 2 open question about FastMCP base_url propagation**: FastMCP's `OpenAPITool.run()` reads `self._client.base_url` fresh on every tool invocation (verified from installed source code, line: `base_url = str(self._client.base_url) or "http://localhost"`), and `httpx2.AsyncClient.base_url` is a mutable property (verified by runtime test). This confirms that the ConfigMap file-watcher pattern baked into generated scaffolds correctly propagates backend URL changes to FastMCP-dispatched tool requests, satisfying BACK-03 compliance for all 20 new domain servers.

The second critical finding is a **potential OpenShift version compatibility concern**: RHCL 1.4 requires OCP 4.19+ (verified against Red Hat's supported configurations matrix), but Phase 1/2 used oc CLI 4.18.16. If the cluster itself is OCP 4.18, RHCL 1.4 cannot be installed -- the planner must verify the cluster version as a gating first step. If 4.18, options are: upgrade to 4.19+, or fall back to RHCL 1.3 (supports 4.18 with OSSM 3.2, but contradicts CONTEXT.md D-02's "pin to 1.4.1+" decision, requiring user confirmation).

**Primary recommendation:** Verify cluster version first. If 4.19+: install OSSM 3.3+ and cert-manager 1.19, then RHCL MCP Gateway Operator via OLM. Generate domain servers using the proven CLI for TMF specs (6+5+4 tools), and use CLI-then-merge for the multi-spec domains (NWDAF: 2 specs / 3 tools, CAMARA: 2 specs / 2 tools). Register all 6 backends via the simpler on-premise MCPServerRegistration flow (not the external-server flow -- all backends are in-cluster).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Gateway is RHCL MCP Gateway (OLM Operator), NOT a hand-rolled FastMCP mount() composition server. Supersedes ARCHITECTURE.md's original design.
- **D-02:** Version: pin to RHCL 1.4.1+ (1.4.0 deprecated due to auth failures, instability, memory pressure)
- **D-03:** Technology Preview status accepted (no fallback architecture)
- **D-04:** RHCL Operator, Gateway API provider, and Istio-based data plane provisioned from scratch in Phase 3
- **D-05:** MCP-Telecom registered as a backend behind the same RHCL gateway (single endpoint for all 78 tools)
- **D-06:** Backend registration uses MCPServerRegistration CRD (6 registrations total)
- **D-07:** Per-domain Virtual MCP Servers (TMF, NWDAF, CAMARA, infra/MCP-Telecom), not one flat unified tool list
- **D-08:** AuthPolicy configured in Phase 3 (not deferred)
- **D-09:** 5 new domain servers deploy into otel25-mcp; gateway gets its own namespace
- **D-10:** Each domain server built via Phase 2's conversion CLI, one server per API spec, hand-curated
- **D-11:** Verification against Prism mocks for all 20 new tools; live NextGCore for NWDAF is stretch goal

### Claude's Discretion
- Exact MCPServerRegistration and MCPGatewayExtension resource naming/field values
- New gateway namespace name
- Whether in-cluster registration needs the full "external MCP server" steps (ServiceEntry, TLS, Secret) or a lighter path -- RESOLVED by research: on-premise (in-cluster) flow is sufficient (see Architecture Patterns)
- Exact tool-naming scheme within each per-domain Virtual MCP Server

### Deferred Ideas (OUT OF SCOPE)
None -- wiring MCP-Telecom to real devices, fixing Phase 2 security gaps (CR-01/02/03), and running the SDG pipeline are all later-phase work.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| MCP-01 | Build 6 curated TMF642 alarm management MCP tools | Conversion CLI invocation against tmf642_alarm_v5.0.1.oas.yaml with allowlist for 6 operations; OAS 3.0, direct from_openapi() |
| MCP-02 | Build 5 curated TMF628 performance management MCP tools | Conversion CLI invocation against tmf628_performance_v4.0.0.swagger.json; Swagger 2.0 confirmed working with FastMCP from_openapi() |
| MCP-03 | Build 4 curated TMF621 trouble ticket MCP tools | Conversion CLI invocation against tmf621_troubleticket_v5.0.1.oas.yaml; OAS 3.0, direct from_openapi() |
| MCP-04 | Build 3 curated NWDAF TS 29.520 analytics MCP tools | Two specs (AnalyticsInfo + EventsSubscription); CLI invoked twice then merged into one server via mount() composition |
| MCP-05 | Build 2 curated CAMARA Device Location MCP tools | Two specs (verification + retrieval); CLI invoked twice then merged; Phase 2 already smoke-tested the verification spec |
| MCP-08 | Compose all MCP servers behind Kuadrant MCP Gateway with tool namespacing | RHCL MCP Gateway install via OLM, MCPServerRegistration for 6 backends, MCPVirtualServer for 4 domains, AuthPolicy with JWT |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Domain MCP server generation | Developer tooling (CLI) | -- | openapi_to_mcp.py runs locally, produces server.py scaffolds |
| Domain MCP server runtime | MCP Server (Python/FastMCP, in-cluster) | -- | Each server is a FastMCP process serving Streamable HTTP |
| ConfigMap-based backend routing | MCP Server + OpenShift ConfigMap | -- | File-watcher in server reads volume-mounted ConfigMap; kubelet propagates |
| RHCL Gateway infrastructure | OpenShift Operator (OLM) | Istio/OSSM data plane | Operator deploys controller, broker, router; Istio provides Gateway API + ext_proc |
| Backend registration | RHCL CRDs (MCPServerRegistration) | HTTPRoute (Gateway API) | Each backend has HTTPRoute + MCPServerRegistration |
| Tool curation/namespacing | RHCL CRD (MCPVirtualServer) | -- | Virtual servers filter tools/list per domain |
| Authentication/authorization | RHCL AuthPolicy | Identity Provider (Keycloak) | JWT validation, CEL-based tool-level access control |
| Traffic routing | Envoy proxy (Gateway API) | RHCL ext_proc MCP router | Envoy handles ingress; ext_proc parses MCP protocol for routing |

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard | Confidence |
|---------|---------|---------|--------------|------------|
| `fastmcp` | 4.0.11 | MCP server framework for generated domain servers | Project-wide standard per STACK.md; from_openapi(), RouteMap, Streamable HTTP | HIGH [VERIFIED: PyPI 4.0.11 confirmed] |
| `httpx2` | 2.13.1 | Async HTTP client for backend calls in domain servers | FastMCP 4.x dependency; replaced httpx in FastMCP 4.0 | HIGH [VERIFIED: PyPI 2.13.1 confirmed, FastMCP source imports httpx2] |
| Python | 3.12 | Runtime for domain servers (container) | Project standard per STACK.md | HIGH [CITED: STACK.md] |
| `pyyaml` | 6.0.3 | YAML parsing for specs and allowlists in generated scaffolds | Existing dependency from Phase 2 | HIGH [VERIFIED: PyPI] |
| RHCL MCP Gateway Operator | 1.4.1+ | MCP gateway, MCPServerRegistration, MCPVirtualServer CRDs | CONTEXT.md D-01/D-02 locked decision | HIGH [CITED: RHCL 1.4 install docs] |
| OpenShift Service Mesh | 3.3 or 3.4 | Gateway API provider (Istio control plane) | RHCL 1.4 prerequisite | HIGH [VERIFIED: RHCL supported configs matrix] |
| cert-manager Operator | 1.19 | TLS certificate management for gateways | RHCL 1.4 prerequisite | HIGH [VERIFIED: RHCL supported configs matrix] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pydantic` | >=2.0 | Schema validation in generated scaffolds | FastMCP internal dependency |
| Red Hat build of Keycloak | 26.6 | Identity provider for MCP gateway AuthPolicy | D-08 auth requirement; RHCL 1.4 supported version |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| RHCL 1.4 MCP Gateway | FastMCP mount() composition | mount() is simpler but lacks auth, namespacing, Virtual MCP Server filtering -- user explicitly rejected this in D-01 |
| RHCL 1.4 | RHCL 1.3 | If cluster is OCP 4.18, RHCL 1.3 (supports 4.18 + OSSM 3.2) is the only option without a cluster upgrade; contradicts D-02 |
| OSSM 3.3+ | Built-in OCP Gateway API (4.19+) | OCP 4.19+ ships Gateway API natively, but RHCL explicitly requires OSSM for the Istio control plane and mTLS |
| Keycloak | API key auth | Simpler but less flexible; RHCL docs focus on JWT/OIDC patterns |

**Installation (domain server dependencies):**
```bash
cd mcp/<domain-server>
uv add fastmcp httpx2 pyyaml
```

**Installation (RHCL + prerequisites on OpenShift):**
```bash
# 1. OSSM 3.3+ Operator
oc apply -f ossm-subscription.yaml  # channel: stable, name: servicemeshoperator3

# 2. cert-manager Operator
oc apply -f cert-manager-subscription.yaml  # channel: stable

# 3. RHCL MCP Gateway Operator
oc create ns otel25-gateway
oc apply -n otel25-gateway -f mcp-gateway-subscription.yaml  # channel: preview, source: redhat-operators
```

## Package Legitimacy Audit

> slopcheck was unavailable at research time. All packages below are tagged `[ASSUMED]` and the planner must gate each install behind a `checkpoint:human-verify` task.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| fastmcp | PyPI | ~1.5 yrs | High (PrefectHQ) | github.com/PrefectHQ/fastmcp | N/A | [ASSUMED] -- project STACK.md standard, already used in Phase 2 |
| httpx2 | PyPI | ~1 yr | Growing (Pydantic continuation) | github.com/encode/httpx continuation | N/A | [ASSUMED] -- httpx module rename by encode/Pydantic team |
| pyyaml | PyPI | ~15 yrs | Very high | github.com/yaml/pyyaml | N/A | [ASSUMED] -- standard YAML parser |
| pydantic | PyPI | ~7 yrs | Very high | github.com/pydantic/pydantic | N/A | [ASSUMED] -- industry standard |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

*All packages are well-established ecosystem standards already used in Phase 2. slopcheck was unavailable at research time, so the planner must gate each install behind a `checkpoint:human-verify` task per protocol.*

## Architecture Patterns

### System Architecture Diagram

```
    MCP Client (Phase 4 SDG Pipeline / manual testing)
         |
         |  POST /mcp (JSON-RPC)
         |  + X-Mcp-Virtualserver: otel25-gateway/tmf-tools (optional)
         |  + Authorization: Bearer <JWT>
         v
    +===============================================================+
    |  RHCL MCP Gateway (otel25-gateway namespace)                  |
    |                                                               |
    |  Gateway (gateway.networking.k8s.io/v1)                       |
    |    Listener: mcp (port 8080, HTTP)                            |
    |                                                               |
    |  MCPGatewayExtension ---> auto-creates HTTPRoute /mcp         |
    |    targetRef: Gateway/mcp listener                            |
    |                                                               |
    |  Envoy Proxy (Gateway API data plane)                         |
    |    + ext_proc: MCP Router (parses MCP protocol, sets headers) |
    |    + MCP Broker (consolidates tools, manages sessions)        |
    |                                                               |
    |  AuthPolicy (JWT validation via Keycloak)                     |
    |    authentication: JWT issuerUrl                              |
    |    authorization: CEL tool-level access checks                |
    |                                                               |
    |  MCPVirtualServers:                                           |
    |    tmf-tools    -> tmf642_*, tmf628_*, tmf621_* (15 tools)    |
    |    nwdaf-tools  -> nwdaf_* (3 tools)                          |
    |    camara-tools -> camara_* (2 tools)                         |
    |    infra-tools  -> mcp_telecom_* (58 tools)                   |
    |                                                               |
    |  MCPServerRegistrations (6):                                  |
    |    tmf642   -> HTTPRoute -> svc/mcp-tmf642:8000               |
    |    tmf628   -> HTTPRoute -> svc/mcp-tmf628:8000               |
    |    tmf621   -> HTTPRoute -> svc/mcp-tmf621:8000               |
    |    nwdaf    -> HTTPRoute -> svc/mcp-nwdaf:8000                |
    |    camara   -> HTTPRoute -> svc/mcp-camara:8000               |
    |    telecom  -> HTTPRoute -> svc/mcp-telecom:8000              |
    +===============================================================+
         |                                          |
         | (in-cluster routing)                      |
         v                                          v
    +============================+    +============================+
    |  otel25-mcp namespace      |    |  otel25-backends namespace |
    |                            |    |                            |
    |  mcp-tmf642  (6 tools)  ---+--->|  prism-tmf642:4010         |
    |  mcp-tmf628  (5 tools)  ---+--->|  prism-tmf628:4010         |
    |  mcp-tmf621  (4 tools)  ---+--->|  prism-tmf621:4010         |
    |  mcp-nwdaf   (3 tools)  ---+--->|  prism-nwdaf:4010 OR       |
    |                            |    |  nextgcore-nwdaf:7777      |
    |  mcp-camara  (2 tools)  ---+--->|  prism-camara:4010 +       |
    |                            |    |  prism-camara-retrieval:4010|
    |  mcp-telecom (58 tools)    |    |                            |
    |    (no backend -- D-07)    |    |  ConfigMap: backend-routing |
    +============================+    +============================+
```

### Recommended Project Structure

```
mcp/
  tmf642/                         # TMF642 Alarm Management server
    server.py                     # Generated then hand-curated
    specs/                        # Symlink or copy of vendored spec
    allowlist.yaml                # 6 operations
    Dockerfile
  tmf628/                         # TMF628 Performance Management server
    server.py
    specs/
    allowlist.yaml                # 5 operations
    Dockerfile
  tmf621/                         # TMF621 Trouble Ticket server
    server.py
    specs/
    allowlist.yaml                # 4 operations
    Dockerfile
  nwdaf/                          # NWDAF Analytics server (merged from 2 specs)
    server.py                     # Composed via mount() from 2 from_openapi() calls
    specs/                        # Both AnalyticsInfo and EventsSubscription specs
    allowlist_analytics.yaml      # 1 operation (GET /analytics)
    allowlist_events.yaml         # 2 operations (POST/DELETE /subscriptions)
    Dockerfile
  camara/                         # CAMARA Device Location server (merged from 2 specs)
    server.py                     # Composed via mount() from 2 from_openapi() calls
    specs/                        # Both verification and retrieval specs
    allowlist_verify.yaml         # 1 operation (POST /verify)
    allowlist_retrieve.yaml       # 1 operation (POST /retrieve)
    Dockerfile
  mcp-telecom/                    # Existing from Phase 2 (no changes)
  tooling/                        # Existing conversion CLI from Phase 2
  openshift/
    namespace.yaml                # Existing otel25-mcp namespace
    mcp-tmf642-deployment.yaml    # New: Deployment + Service
    mcp-tmf628-deployment.yaml
    mcp-tmf621-deployment.yaml
    mcp-nwdaf-deployment.yaml
    mcp-camara-deployment.yaml
    mcp-telecom-deployment.yaml   # Existing from Phase 2
    mcp-telecom-secret.yaml       # Existing from Phase 2
gateway/
  openshift/
    namespace.yaml                # otel25-gateway namespace
    ossm-subscription.yaml        # OSSM 3.3+ Operator Subscription
    istio-cni.yaml                # IstioCNI CR
    istio.yaml                    # Istio CR (control plane)
    cert-manager-subscription.yaml
    mcp-gateway-subscription.yaml # RHCL MCP Gateway Operator
    gateway.yaml                  # Gateway object with mcp listener
    mcp-gateway-extension.yaml    # MCPGatewayExtension CR
    reference-grant.yaml          # ReferenceGrant (cross-namespace)
    mcpsr-tmf642.yaml             # MCPServerRegistration for TMF642
    mcpsr-tmf628.yaml
    mcpsr-tmf621.yaml
    mcpsr-nwdaf.yaml
    mcpsr-camara.yaml
    mcpsr-telecom.yaml
    httproute-tmf642.yaml         # HTTPRoute per backend
    httproute-tmf628.yaml
    httproute-tmf621.yaml
    httproute-nwdaf.yaml
    httproute-camara.yaml
    httproute-telecom.yaml
    mcpvs-tmf.yaml                # MCPVirtualServer for TMF domain
    mcpvs-nwdaf.yaml
    mcpvs-camara.yaml
    mcpvs-infra.yaml
    auth-policy.yaml              # AuthPolicy for JWT auth
    auth-policy-authz.yaml        # AuthPolicy for tool-level authorization
scripts/
  verify-domain-tools.sh          # Per-tool verification against Prism
  verify-gateway.sh               # End-to-end gateway verification
```

### Pattern 1: On-Premise MCP Server Registration (In-Cluster)

**What:** Register an in-cluster MCP server with the RHCL gateway using HTTPRoute + MCPServerRegistration. This is the simpler path -- no ServiceEntry, TLS settings, or external-server-specific resources needed.

**When:** All 6 backends are in-cluster Services in `otel25-mcp`.

**Resolution of CONTEXT.md discretion item:** The "external MCP server" registration flow (ServiceEntry, TLS, Secret, per-server AuthPolicy) is for backends OUTSIDE the cluster. Since all 6 MCP backends are in-cluster Services, the on-premise flow applies.

**Step 1 -- Create HTTPRoute pointing to backend Service:**
```yaml
# Source: RHCL 1.4 docs "Register on-premise MCP servers"
# [CITED: docs.redhat.com/en/documentation/red_hat_connectivity_link/1.4/html/register_mcp_servers_and_create_policies/]
apiVersion: gateway.networking.k8s.io/v1
kind: HTTPRoute
metadata:
  name: mcp-tmf642-route
  namespace: otel25-gateway
  labels:
    mcp-server: "true"
spec:
  parentRefs:
  - name: mcp-gateway
    namespace: otel25-gateway
  rules:
  - backendRefs:
    - name: mcp-tmf642
      namespace: otel25-mcp
      port: 8000
```

**Step 2 -- Create MCPServerRegistration:**
```yaml
# Source: RHCL 1.4 docs "Register on-premise MCP servers"
# [CITED: docs.redhat.com/en/documentation/red_hat_connectivity_link/1.4/html/register_mcp_servers_and_create_policies/]
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
  # path defaults to /mcp (matches FastMCP Streamable HTTP endpoint)
```

**MCPServerRegistration Schema (key fields):**
[CITED: docs.redhat.com/en/documentation/red_hat_connectivity_link/1.4/html/register_mcp_servers_and_create_policies/]

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `spec.prefix` | String | No | Prefix for tool names (e.g., `tmf642_list_alarms`). Lowercase alphanumeric + underscores only. Immutable after creation. |
| `spec.targetRef` | TargetReference | Yes | Points to the backend HTTPRoute |
| `spec.path` | String | No | MCP endpoint path on backend (default: `/mcp`) |
| `spec.credentialRef` | SecretReference | No | Secret with auth credentials for backend (label `mcp.kuadrant.io/secret=true` required) |

**Status fields:**
- `status.conditions` -- Ready condition with reasons
- `status.discoveredTools` -- Integer count of tools discovered

**Verification:**
```bash
oc get mcpsr -A
# Expected: READY=True, TOOLS=6 for tmf642, etc.
```

### Pattern 2: Virtual MCP Servers for Domain Curation

**What:** MCPVirtualServer CRs that filter tools/list and prompts/list to show only a curated subset, selected via `X-Mcp-Virtualserver` header.

**When:** D-07 requires per-domain virtual servers (TMF, NWDAF, CAMARA, infra).

**How it works:**
[CITED: docs.redhat.com/en/documentation/red_hat_connectivity_link/1.4/html/register_mcp_servers_and_create_policies/]
- Virtual servers filter `tools/list` and `prompts/list` responses only -- they do NOT change call routing or authorization
- Clients select a virtual server via `X-Mcp-Virtualserver: <namespace>/<name>` header
- Without the header, clients see ALL tools from all registered backends
- Tools are listed by their PREFIXED names (e.g., `tmf642_list_alarms`)

```yaml
# Source: RHCL 1.4 docs "Create virtual MCP servers"
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
  - tmf642_acknowledge_alarm
  - tmf642_clear_alarm
  - tmf642_add_comment
  - tmf642_subscribe_alarms
  - tmf628_list_collection_jobs
  - tmf628_create_on_demand_collection
  - tmf628_get_collection_status
  - tmf628_get_tracking_records
  - tmf628_get_tracking_record
  - tmf621_create_ticket
  - tmf621_update_ticket
  - tmf621_get_ticket
  - tmf621_list_tickets
```

**Important:** The tool names in the virtual server spec must match the EXACT prefixed names that appear after MCPServerRegistration discovers them. The prefix + the operationId-derived tool name must match. Run `oc get mcpsr -A -o yaml` to see `discoveredTools` and exact names before authoring virtual server configs.

### Pattern 3: Multi-Spec Domain Server via FastMCP mount()

**What:** Composing two `from_openapi()` server instances into one domain server when the API family spans multiple specs.

**When:** NWDAF (AnalyticsInfo + EventsSubscription = 2 specs) and CAMARA (verification + retrieval = 2 specs).

**Approach:**
```python
# Generated by CLI then hand-merged
# Source: FastMCP docs + project conversion CLI
from fastmcp import FastMCP
import httpx2

# Each spec gets its own client (can have different base_url via ConfigMap)
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

# Compose into one server
mcp = FastMCP("NWDAF")
mcp.mount("analytics", analytics_mcp)
mcp.mount("events", events_mcp)
```

**Note on mount() prefix:** `mount("analytics", ...)` prefixes tool names with `analytics_`. Combined with the MCPServerRegistration prefix `nwdaf`, the final tool names would be `nwdaf_analytics_get_nwdaf_analytics`. This double-prefixing may be undesirable. Alternative: mount with empty prefix or import tools directly. The planner should determine the final naming scheme, considering that the MCPServerRegistration prefix already provides the domain context.

**Alternative for small tool counts:** For NWDAF (3 tools) and CAMARA (2 tools), hand-writing explicit `@mcp.tool()` decorators that call httpx2 directly may be cleaner than composing two from_openapi() instances. This avoids mount() prefix complexity and gives full control over tool names, descriptions, and URL construction.

### Pattern 4: RHCL MCP Gateway Installation Sequence

**What:** Full installation sequence for the gateway infrastructure from scratch.

**When:** D-04 commits to provisioning all this in Phase 3.

**Prerequisites verified:**
[VERIFIED: RHCL 1.4 supported configurations matrix at access.redhat.com/articles/7092611]
- OCP 4.19, 4.20, 4.21, or 4.22
- OSSM 3.3 or 3.4
- cert-manager Operator 1.19
- (Optional) Red Hat build of Keycloak 26.6 for auth

**Installation sequence:**

1. **Verify OCP version** (CRITICAL -- gates all subsequent steps):
```bash
oc version --short  # Must show Server Version 4.19+
```

2. **Install OSSM 3.3+ Operator:**
[CITED: developers.redhat.com/articles/2025/12/09/integrate-openshift-gateway-api-openshift-service-mesh]
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

3. **Create IstioCNI** (must come first -- handles network interception):
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

4. **Create Istio control plane:**
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

5. **Install cert-manager Operator** (from OperatorHub, channel: stable)

6. **Install RHCL MCP Gateway Operator:**
[CITED: docs.redhat.com/en/documentation/red_hat_connectivity_link/1.4/html/install_the_mcp_gateway/]
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

7. **Create Gateway object** with mcp listener:
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

8. **Create MCPGatewayExtension:**
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

9. **Verify:** `oc wait --for=condition=Ready mcpgatewayextension/mcp-gateway-ext -n otel25-gateway`

**MCPGatewayExtension key fields:**
[CITED: docs.redhat.com/en/documentation/red_hat_connectivity_link/1.4/html/install_the_mcp_gateway/]

| Field | Description | Default |
|-------|-------------|---------|
| `spec.targetRef.sectionName` | Gateway listener name (REQUIRED) | -- |
| `spec.publicHost` | Override public hostname | Derived from listener |
| `spec.privateHost` | Internal hair-pin host | `<gateway>-istio.<ns>.svc.cluster.local:<port>` |
| `spec.backendPingIntervalSeconds` | Backend health check interval | 60 (range: 10-7200) |
| `spec.trustedHeadersKey` | JWT signing key for x-mcp-authorized header | -- |
| `spec.httpRouteManagement` | Auto-create /mcp HTTPRoute | Enabled |
| `spec.sessionStore` | Redis Secret for session persistence | -- (in-memory) |

### Pattern 5: AuthPolicy for MCP Gateway

**What:** JWT authentication + tool-level authorization via RHCL AuthPolicy CRs.

**When:** D-08 requires auth configured in Phase 3.

**Architecture:**
[CITED: docs.redhat.com/en/documentation/red_hat_connectivity_link/1.4/html/register_mcp_servers_and_create_policies/]
- Authentication AuthPolicy targets the `mcp` listener -- validates JWT tokens
- Authorization AuthPolicy targets the `mcps` listener (internal) -- CEL-based tool access checks
- Both require an identity provider (Keycloak) issuing JWTs with `resource_access` claims
- Tool roles in JWT use the MCPServerRegistration namespaced name as the client ID

**Authentication AuthPolicy example:**
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

**Note:** Full tool-level authorization requires:
1. Keycloak realm with client roles per MCPServerRegistration
2. Authorization AuthPolicy with CEL expressions on the `mcps` listener
3. (Optional) Trusted headers signing for tools/list filtering

For Phase 3's scope (a WG training-data pipeline, not production), a simpler auth-only (no per-tool authz) configuration may suffice. The planner should determine the appropriate depth.

### Anti-Patterns to Avoid

- **Using the "external MCP server" registration flow for in-cluster backends:** The external flow (ServiceEntry, TLS, Secret, per-server AuthPolicy) adds unnecessary complexity. In-cluster Services only need HTTPRoute + MCPServerRegistration. [CITED: RHCL docs distinguish on-premise vs external flows]
- **One flat MCPVirtualServer with all 78 tools:** D-07 explicitly requires per-domain separation. A single virtual server overwhelms LLMs with tool choices. [CITED: RHCL docs: "risks overwhelming LLMs and AI agents with too many tool and prompt choices"]
- **Hand-rolling a FastMCP mount() gateway INSTEAD of RHCL:** D-01 explicitly supersedes the original ARCHITECTURE.md design. FastMCP mount() composition may still be used WITHIN individual domain servers (e.g., NWDAF merging 2 specs), but the GATEWAY is RHCL.
- **Installing RHCL 1.4.0:** Deprecated due to auth failures, instability, and memory pressure. Must use 1.4.1+. [CITED: RHCL install guide deprecation notice]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| MCP gateway / tool aggregation | FastMCP mount() proxy server | RHCL MCP Gateway | Auth, namespacing, virtual servers, revocation built-in; D-01 locked decision |
| Tool namespace collision avoidance | Custom prefix logic | MCPServerRegistration `prefix` field | Gateway automatically prefixes all tools from each registration |
| Tool curation / filtering | Custom tools/list wrapper | MCPVirtualServer CR | Declarative YAML, filterable by header, combined with auth-based filtering |
| Gateway auth | Custom JWT middleware | RHCL AuthPolicy CR | Integrated with Envoy ext_proc, supports OIDC, CEL authorization |
| OpenAPI-to-MCP conversion | Manual tool definitions | Phase 2 conversion CLI (`openapi_to_mcp.py`) | Proven against CAMARA and synthetic specs; generates BACK-03-compliant scaffolds |
| Backend URL switching | Restart pods or env vars | ConfigMap file-watcher (baked into scaffolds) | Live switching per BACK-03; verified to propagate through FastMCP from_openapi() |
| Gateway API data plane | Custom Envoy config | OSSM 3.3+ (Istio Operator) | Managed, supported, required by RHCL |

**Key insight:** RHCL MCP Gateway handles the full gateway stack (routing, auth, namespacing, virtual servers). Phase 3's job is configuration (CRDs), not implementation.

## Common Pitfalls

### Pitfall 1: OpenShift Cluster Version Incompatibility with RHCL 1.4

**What goes wrong:** RHCL 1.4 Operator install fails or catalog entry is missing because the cluster is OCP 4.18 (not 4.19+).
**Why it happens:** RHCL 1.4 only supports OCP 4.19, 4.20, 4.21, 4.22. Phase 1/2 used oc CLI 4.18.16 -- the cluster version may be 4.18.
**How to avoid:** First task in planning MUST be `oc version` to check cluster version. If 4.18: either upgrade to 4.19+ or use RHCL 1.3 (supports 4.18 + OSSM 3.2), but RHCL 1.3 contradicts D-02 and requires user confirmation.
**Warning signs:** `oc apply -f mcp-gateway-subscription.yaml` returns "no matching ClusterServiceVersion" or subscription stays in `UpgradePending`.
[VERIFIED: RHCL supported configurations matrix, access.redhat.com/articles/7092611]

### Pitfall 2: Dual Istio Control Plane Conflict

**What goes wrong:** The GatewayClass `openshift-default` triggers an auto-provisioned Istio instance in `openshift-ingress`, creating a SECOND mesh separate from the user-installed OSSM Istio in `istio-system`. Each mesh has its own CA, causing mTLS failures between the Gateway data plane and mesh-enrolled backend pods.
**Why it happens:** On OCP 4.19+, the Ingress Operator auto-creates a lightweight Istio for the Gateway API, distinct from any user-installed OSSM.
**How to avoid:** Follow the OSSM + Gateway API integration guide (shared root CA setup), OR ensure the MCP gateway namespace and backend namespace have matching mesh enrollment. The RHCL docs reference the `<gateway>-istio.<ns>.svc.cluster.local` service pattern, indicating awareness of this architecture.
**Warning signs:** MCPServerRegistration shows READY but tool calls return connection errors or TLS handshake failures.
[CITED: developers.redhat.com/articles/2025/12/09/integrate-openshift-gateway-api-openshift-service-mesh]

### Pitfall 3: MCPServerRegistration Prefix Naming Constraints

**What goes wrong:** `oc apply` rejects the MCPServerRegistration because the `prefix` field contains hyphens, uppercase letters, or starts with an underscore.
**Why it happens:** The prefix field enforces a strict regex: lowercase letters (a-z), digits (0-9), and underscores (_) only, must start with a letter or digit. The CRD schema enforces this.
**How to avoid:** Use simple prefixes: `tmf642`, `tmf628`, `tmf621`, `nwdaf`, `camara`, `telecom`. No hyphens, no `mcp-telecom` (use `telecom` or `mcp_telecom`).
**Warning signs:** Validation error on `oc apply`.
[CITED: docs.redhat.com/en/documentation/red_hat_connectivity_link/1.4/html/register_mcp_servers_and_create_policies/]

### Pitfall 4: NWDAF Path Difference Between Prism and NextGCore

**What goes wrong:** The NWDAF MCP server works against Prism but fails against NextGCore because the analytics endpoint is at different paths.
**Why it happens:** The NWDAF AnalyticsInfo spec defines path `/analytics` relative to server `{apiRoot}/nnwdaf-analyticsinfo/v1`. Prism strips the server base path and serves at `/analytics`. NextGCore serves at the full path `/nnwdaf-analyticsinfo/v1/analytics`. FastMCP from_openapi() ignores the OpenAPI `servers` field (known limitation, issue #1681).
**How to avoid:** FastMCP's `_build_url()` joins `base_url.rstrip("/") + "/"` with `path.lstrip("/")`, making the path relative. For NextGCore, include the server base path in the ConfigMap: `NWDAF_BASE_URL: "http://nextgcore:7777/nnwdaf-analyticsinfo/v1"`. For Prism, use just the host: `NWDAF_BASE_URL: "http://prism-nwdaf:4010"`. Verified by URL join test:
```
urljoin("http://nextgcore:7777/nnwdaf-analyticsinfo/v1/", "analytics")
= "http://nextgcore:7777/nnwdaf-analyticsinfo/v1/analytics"  (correct)
```
**Warning signs:** NWDAF tool calls return 404 after switching ConfigMap to NextGCore.
**Phase 3 impact:** Low -- D-11 says Prism verification only. NextGCore is a stretch goal.
[VERIFIED: FastMCP 4.0.11 source code inspection + Python urljoin test]

### Pitfall 5: Multi-Spec NWDAF/CAMARA Server Complexity

**What goes wrong:** Generated scaffolds for NWDAF and CAMARA each handle one spec, but the domain servers need to serve tools from TWO specs (AnalyticsInfo + EventsSubscription for NWDAF; verify + retrieve for CAMARA).
**Why it happens:** The conversion CLI takes one spec + one allowlist per invocation. Multi-spec domains need post-generation merging.
**How to avoid:** Three options (planner decides):
  1. Run CLI twice, manually merge the two generated server.py files using FastMCP `mount()` composition
  2. Run CLI twice, extract the RouteMap and spec references from each, write a single server.py that calls `from_openapi()` twice
  3. For small tool counts (NWDAF=3, CAMARA=2), hand-write explicit `@mcp.tool()` decorators instead of using from_openapi()
**Warning signs:** Generated scaffold only lists half the expected tools.

### Pitfall 6: FastMCP 4.x httpx2 Migration

**What goes wrong:** Generated scaffolds use `import httpx2` (correct for FastMCP 4.x), but developers unfamiliar with the migration attempt to use `import httpx` in new code or tests, causing type mismatches or silent failures.
**Why it happens:** FastMCP 4.0 replaced httpx with httpx2 (API-compatible module rename). httpx2 types and httpx types are NOT interchangeable at runtime.
**How to avoid:** All new domain server code uses `import httpx2`. Tests that test FastMCP-integrated behavior use `httpx2`. The existing Phase 2 unit tests (`test_configmap_watcher.py`) use `httpx` for isolated watcher testing -- this is fine since they don't test FastMCP integration. But any test that exercises from_openapi() behavior must use httpx2.
**Warning signs:** `FastMCPDeprecationWarning` in logs when passing httpx.AsyncClient to from_openapi().
[VERIFIED: FastMCP 4.0.11 source imports httpx2; dev.to/wolfejam/fastmcp-3-4-migration]

### Pitfall 7: Cross-Namespace HTTPRoute References

**What goes wrong:** HTTPRoute in otel25-gateway cannot reference backend Service in otel25-mcp; requests return 503.
**Why it happens:** Gateway API requires explicit cross-namespace grants. The HTTPRoute `backendRefs` referencing a Service in another namespace needs a `ReferenceGrant` in the target namespace.
**How to avoid:** Create a ReferenceGrant in `otel25-mcp` allowing `HTTPRoute` from `otel25-gateway` to reference Services:
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
**Warning signs:** HTTPRoute status shows `BackendNotPermitted`.
[CITED: RHCL install docs ReferenceGrant section]

## Code Examples

### Example 1: Complete TMF642 Allowlist Config

```yaml
# mcp/tmf642/allowlist.yaml
# Source: fault_prediction_api_map.md + allowlist_schema.py [VERIFIED: codebase]
server_name: "mcp-tmf642"
spec_path: "specs/tmf642_alarm_v5.0.1.oas.yaml"
backend_env_var: "TMF642_BASE_URL"
operations:
  - path: "/alarm"
    methods: ["GET"]
    mcp_type: "TOOL"
  - path: "/alarm/{id}"
    methods: ["GET"]
    mcp_type: "TOOL"
  - path: "/alarm/{id}"
    methods: ["PATCH"]
    mcp_type: "TOOL"
  - path: "/hub"
    methods: ["POST"]
    mcp_type: "TOOL"
```

Note: The TMF642 spec has 6 desired tools, but some map to the same path+method with different semantics (acknowledge vs clear vs comment all use PATCH /alarm/{id}). The from_openapi() RouteMap matches by path+method, so a single PATCH /alarm/{id} RouteMap creates ONE tool, not three. For 6 distinct tools matching the API map, the generated scaffold must be hand-curated post-generation to split the PATCH tool into 3 explicit @mcp.tool() decorators.

### Example 2: CLI Invocation to Generate TMF642 Server

```bash
# From project root
cd mcp/tooling
python openapi_to_mcp.py \
  --spec ../../backends/specs/tmf642_alarm_v5.0.1.oas.yaml \
  --allowlist ../tmf642/allowlist.yaml \
  --output ../tmf642/server.py
```
[VERIFIED: CLI interface from mcp/tooling/openapi_to_mcp.py codebase]

### Example 3: Gateway Endpoint Verification (curl)

```bash
# Source: RHCL 1.4 install docs verification section
# [CITED: docs.redhat.com/en/documentation/red_hat_connectivity_link/1.4/html/install_the_mcp_gateway/]

# Initialize MCP session
curl -s -D /tmp/mcp_headers -X POST http://mcp.apps.<cluster>/mcp \
  -H "Content-Type: application/json" \
  -H "Accept: application/json, text/event-stream" \
  -d '{"jsonrpc": "2.0", "id": 1, "method": "initialize"}'

# Extract session ID
SESSION_ID=$(grep -i "mcp-session-id:" /tmp/mcp_headers | cut -d' ' -f2 | tr -d '\r')

# List all tools through gateway
curl -X POST http://mcp.apps.<cluster>/mcp \
  -H "Content-Type: application/json" \
  -H "mcp-session-id: $SESSION_ID" \
  -d '{"jsonrpc": "2.0", "id": 2, "method": "tools/list"}' | jq '.result.tools[].name'

# List tools for TMF domain only via Virtual MCP Server
curl -X POST http://mcp.apps.<cluster>/mcp \
  -H "Content-Type: application/json" \
  -H "mcp-session-id: $SESSION_ID" \
  -H "X-Mcp-Virtualserver: otel25-gateway/tmf-tools" \
  -d '{"jsonrpc": "2.0", "id": 3, "method": "tools/list"}' | jq '.result.tools[].name'
```

### Example 4: Domain Server Deployment YAML (mirrors Phase 2 pattern)

```yaml
# mcp/openshift/mcp-tmf642-deployment.yaml
# Source: Phase 2 mcp-telecom-deployment.yaml pattern [VERIFIED: codebase]
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-tmf642
  namespace: otel25-mcp
  labels:
    app: mcp-tmf642
    layer: mcp
    domain: tmf
spec:
  replicas: 1
  selector:
    matchLabels:
      app: mcp-tmf642
  template:
    metadata:
      labels:
        app: mcp-tmf642
        layer: mcp
        domain: tmf
    spec:
      containers:
      - name: mcp-tmf642
        image: image-registry.openshift-image-registry.svc:5000/otel25-mcp/mcp-tmf642:latest
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
        volumeMounts:
        - name: backend-routing
          mountPath: /config/backend-routing
          readOnly: true
      volumes:
      - name: backend-routing
        configMap:
          name: backend-routing
---
apiVersion: v1
kind: Service
metadata:
  name: mcp-tmf642
  namespace: otel25-mcp
  labels:
    app: mcp-tmf642
    layer: mcp
spec:
  selector:
    app: mcp-tmf642
  ports:
  - port: 8000
    targetPort: 8000
    protocol: TCP
  type: ClusterIP
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| FastMCP mount() for gateway composition | RHCL MCP Gateway (Operator) | CONTEXT.md D-01 (2026-10-04) | Gateway is an OpenShift Operator, not hand-rolled code |
| httpx for FastMCP backend calls | httpx2 for FastMCP 4.x | FastMCP 4.0 release | Module rename; API-compatible but types not interchangeable |
| fastmcp 4.0.10 | fastmcp 4.0.11 | Recent PyPI release | Latest version; minor fixes |
| httpx2 2.5 minimum | httpx2 2.13.1 latest | Ongoing development | Use latest for bug fixes |
| httpx base_url immutable | httpx2 base_url mutable via property | Both versions | Setter works; verified for ConfigMap file-watcher pattern |

**Deprecated/outdated:**
- `from mcp.server.fastmcp import FastMCP`: Removed in `mcp` SDK v2.0. Use `from fastmcp import FastMCP` (standalone).
- RHCL 1.4.0: Deprecated; use 1.4.1+.

## Key Research Finding: FastMCP base_url Propagation (RESOLVED)

**This resolves the open question from Phase 2 (STATE.md, 02-RESEARCH.md Open Question 1).**

**Question:** Does FastMCP's `from_openapi()` re-read the httpx client's `base_url` per-request, or freeze it at construction time?

**Answer:** Re-reads per-request. [VERIFIED: FastMCP 4.0.11 installed source code]

**Evidence chain:**

1. `OpenAPITool.run()` (fastmcp/server/providers/openapi.py):
```python
base_url = str(self._client.base_url) or "http://localhost"
directed_request = self._director.build(self._route, arguments, base_url)
```
The client reference (`self._client`) is the same object passed to `from_openapi()`. `base_url` is read from the live client property on every tool call, not cached.

2. `RequestDirector._build_url()` (fastmcp/utilities/openapi/director.py):
```python
return urljoin(base_url.rstrip("/") + "/", url_path.lstrip("/"))
```
The `base_url` parameter comes from step 1 and is used directly in URL construction.

3. `httpx2.AsyncClient.base_url` is a mutable property:
```python
client = httpx2.AsyncClient(base_url="http://old:4010")
client.base_url = "http://new:4010"  # Property setter works
str(client.base_url)  # Returns "http://new:4010"
```
[VERIFIED: runtime test]

**Conclusion:** The ConfigMap file-watcher pattern (already baked into generated scaffolds) correctly propagates backend URL changes to FastMCP-dispatched tool requests. No need to recreate the FastMCP server instance on ConfigMap change. BACK-03 compliance is confirmed for all 20 new domain servers.

**Recommended update:** Remove the TODO comment in the generated scaffold template (`openapi_to_mcp.py` line 82-85) and the corresponding STATE.md blocker entry for this concern.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | OCP cluster version is 4.19+ (compatible with RHCL 1.4) | Pitfall 1 | HIGH -- if 4.18, RHCL 1.4 cannot install. Planner must verify with `oc version` as first task. |
| A2 | FastMCP from_openapi() handles Swagger 2.0 specs (TMF628) | Phase Requirements MCP-02 | LOW -- verified by runtime test: Swagger 2.0 dict accepted without error [VERIFIED: runtime test] |
| A3 | Keycloak will be deployed for RHCL AuthPolicy | Pattern 5 | MEDIUM -- D-08 requires auth but doesn't specify IdP. Keycloak is RHCL's documented/supported IdP. If deploying Keycloak is too heavy for this WG project, simpler auth (API key via AuthPolicy) may work. |
| A4 | The TMF642 spec has distinct operationIds for list/get/patch operations that map to 6 unique from_openapi() tools | Example 1 | MEDIUM -- PATCH /alarm/{id} may generate only 1 tool covering acknowledge/clear/comment. Hand-curation will be needed to split into 3 tools. |
| A5 | FastMCP mount() composition for multi-spec servers preserves tool functionality | Pattern 3 | LOW -- mount() is a core FastMCP feature documented for server composition. But double-prefixing (mount prefix + MCPServerRegistration prefix) needs verification. |
| A6 | OSSM 3.3+ provides the correct Istio version for RHCL 1.4 on the target cluster | Standard Stack | LOW -- RHCL supported configs matrix explicitly lists OSSM 3.3 and 3.4. |
| A7 | httpx2 is a legitimate package (Pydantic team continuation of httpx) | Package Audit | LOW -- httpx2 is imported directly by FastMCP 4.0.11 (verified from installed source). PyPI shows 2.13.1 with active development. |

## Open Questions

1. **OCP cluster version**
   - What we know: Phase 1/2 used oc CLI 4.18.16. RHCL 1.4 requires OCP 4.19+.
   - What's unclear: The actual cluster server version (CLI and cluster can differ).
   - Recommendation: `oc version` as the gating first task. If 4.18, escalate to user for D-02 reconsideration.
   - **RESOLVED:** OCP 4.20.39 confirmed >= 4.19 required. Version-check gate implemented in 03-04 Task 1 Step 0.

2. **Keycloak deployment scope**
   - What we know: RHCL AuthPolicy uses JWT from an OIDC provider. Keycloak 26.6 is the supported IdP.
   - What's unclear: Whether deploying Keycloak (a full IdP) is within Phase 3's scope for a WG training pipeline.
   - Recommendation: Start with simple auth (if RHCL supports API key auth without full OIDC). If not, deploy a minimal Keycloak instance. D-08 says "configured now", so some auth must be set up.
   - **RESOLVED:** Full Keycloak deployed (minimal instance, ephemeral PostgreSQL). RHCL AuthPolicy requires OIDC/JWT; API key auth alone is insufficient. Implemented in 03-04 Task 1 Steps 6-7 via configure-keycloak.sh.

3. **TMF642 PATCH tool splitting**
   - What we know: The API map lists 3 distinct PATCH operations on /alarm/{id} (acknowledge, clear, comment). FastMCP from_openapi() creates one tool per unique path+method combination.
   - What's unclear: Exact tool names generated by from_openapi() from the TMF642 spec.
   - Recommendation: Generate the scaffold first, inspect tools/list output, then hand-curate to split the PATCH tool if needed.
   - **RESOLVED:** Hand-curation approach adopted. from_openapi() generates 1 PATCH tool; 03-02 Task 1 Step 4d adds 3 explicit @mcp.tool() functions (acknowledge_alarm, clear_alarm, add_comment) after the from_openapi() call, totaling 6 tools.

4. **NWDAF EventsSubscription spec bundling**
   - What we know: The AnalyticsInfo spec is already bundled (external refs inlined). The EventsSubscription spec (rel16) may have external $ref links.
   - What's unclear: Whether FastMCP from_openapi() can handle external $ref references, or if bundling is needed.
   - Recommendation: Try the rel16 spec first. If $ref resolution fails, bundle it using the same process as the AnalyticsInfo bundled spec.
   - **RESOLVED:** Per D-10a, NWDAF uses hand-written @mcp.tool() decorators (not from_openapi()), bypassing the $ref resolution concern entirely. Both specs are copied into mcp/nwdaf/specs/ for reference but not loaded via from_openapi().

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| Python | Domain servers, CLI | Yes | 3.14.6 (local); 3.12 target in containers | Use 3.12-slim Docker base |
| uv | Dependency management | Yes | 0.9.28 | pip (slower but functional) |
| oc | OpenShift deployment | Yes | 4.18.16 client | -- (required, no fallback) |
| podman | Container builds | Yes | 5.6.1 | -- |
| OpenShift cluster | Deployment target | Assumed (Phase 1/2 deployed) | **UNKNOWN -- must verify** | -- (required) |
| OperatorHub (redhat-operators) | OSSM, cert-manager, RHCL | Assumed (standard OCP feature) | -- | -- (required) |
| Keycloak | AuthPolicy IdP | Not installed | -- | API key auth if supported |

**Missing dependencies with no fallback:**
- OpenShift cluster version must be 4.19+ for RHCL 1.4 (verify before planning)

**Missing dependencies with fallback:**
- Keycloak not installed; could use simpler auth or deploy a minimal instance

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest >= 8.0 (project standard) |
| Config file | Per-server `pytest.ini` or shared in `mcp/` |
| Quick run command | `cd mcp/<server> && uv run pytest tests/ -x --timeout=30` |
| Full suite command | `cd mcp/<server> && uv run pytest tests/ -v` + `scripts/verify-domain-tools.sh` + `scripts/verify-gateway.sh` |

### Phase Requirements -> Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| MCP-01 | 6 TMF642 tools listed by server | smoke | `curl POST localhost:8000/mcp tools/list \| jq '.result.tools \| length' == 6` | Wave 0 |
| MCP-01 | Each TMF642 tool returns valid response from Prism | integration | `scripts/verify-domain-tools.sh tmf642` | Wave 0 |
| MCP-02 | 5 TMF628 tools listed by server | smoke | same pattern, == 5 | Wave 0 |
| MCP-02 | Each TMF628 tool returns valid response from Prism | integration | `scripts/verify-domain-tools.sh tmf628` | Wave 0 |
| MCP-03 | 4 TMF621 tools listed by server | smoke | same pattern, == 4 | Wave 0 |
| MCP-03 | Each TMF621 tool returns valid response from Prism | integration | `scripts/verify-domain-tools.sh tmf621` | Wave 0 |
| MCP-04 | 3 NWDAF tools listed by server | smoke | same pattern, == 3 | Wave 0 |
| MCP-04 | Each NWDAF tool returns valid response from Prism | integration | `scripts/verify-domain-tools.sh nwdaf` | Wave 0 |
| MCP-05 | 2 CAMARA tools listed by server | smoke | same pattern, == 2 | Wave 0 |
| MCP-05 | Each CAMARA tool returns valid response from Prism | integration | `scripts/verify-domain-tools.sh camara` | Wave 0 |
| MCP-08a | Gateway initialize returns valid JSON-RPC | smoke | `scripts/verify-gateway.sh initialize` | Wave 0 |
| MCP-08b | All 78 tools visible via gateway tools/list | integration | `scripts/verify-gateway.sh tools-list` | Wave 0 |
| MCP-08c | TMF virtual server filters to 15 tools | integration | `scripts/verify-gateway.sh virtual-tmf` | Wave 0 |
| MCP-08d | Tool call through gateway returns backend response | e2e | `scripts/verify-gateway.sh tool-call` | Wave 0 |

### Sampling Rate
- **Per task commit:** Quick smoke test for the specific server being built
- **Per wave merge:** Full suite for all completed servers + gateway verification
- **Phase gate:** All 20 tools individually callable, gateway composes all 78, virtual servers filter correctly

### Wave 0 Gaps
- [ ] `scripts/verify-domain-tools.sh` -- parameterized per-domain verification
- [ ] `scripts/verify-gateway.sh` -- gateway endpoint verification (initialize, tools/list, virtual server, tool call)
- [ ] Per-server `tests/` directories with unit tests for hand-curated tool customizations

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | Yes | RHCL AuthPolicy with JWT (D-08) |
| V3 Session Management | Yes (limited) | RHCL gateway handles MCP sessions; MCPGatewayExtension sessionStore |
| V4 Access Control | Yes | MCPVirtualServer filtering + AuthPolicy CEL authorization |
| V5 Input Validation | Yes | Pydantic via FastMCP tool parameters; OpenAPI schema validation |
| V6 Cryptography | Yes (limited) | TLS termination at Gateway; ECDSA signing for trusted headers |

### Known Threat Patterns for RHCL MCP Gateway + FastMCP

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Unauthorized tool invocation via exposed gateway | Elevation of Privilege | AuthPolicy JWT validation on mcp listener |
| Tool-level privilege escalation | Elevation of Privilege | AuthPolicy authorization with CEL on mcps listener |
| Tool enumeration by unauthorized users | Information Disclosure | MCPVirtualServer + x-mcp-authorized header filtering |
| SSRF via path parameter injection in from_openapi() | Tampering | FastMCP 3.2.0+ URL-encodes path parameters (CVE-2026-32871 fixed) |
| Backend URL injection via ConfigMap | Tampering | URL validation in file-watcher (http/https prefix check, per T-02-04) |
| Token replay after role revocation | Elevation of Privilege | Token expiry via IdP (Keycloak Access Token Lifespan); not instant revocation |

## Project Constraints (from CLAUDE.md)

- Never push `.gitignore` files to GitHub repos -- keep local only
- Never push blog drafts or personal notes
- When staging files, always review what's being added -- prefer explicit file paths over `git add .`
- Before executing a recommendation, re-read the exact identifier and confirm command matches verbatim

## Sources

### Primary (HIGH confidence)

- **RHCL 1.4 MCP Gateway Install Guide** -- [docs.redhat.com/en/documentation/red_hat_connectivity_link/1.4/html/install_the_mcp_gateway/](https://docs.redhat.com/en/documentation/red_hat_connectivity_link/1.4/html/install_the_mcp_gateway/) -- OLM install, Gateway object, MCPGatewayExtension CR full schema, HTTPRoute auto-creation, DNS management, verification
- **RHCL 1.4 Register MCP Servers and Create Policies** -- [docs.redhat.com/en/documentation/red_hat_connectivity_link/1.4/html/register_mcp_servers_and_create_policies/](https://docs.redhat.com/en/documentation/red_hat_connectivity_link/1.4/html/register_mcp_servers_and_create_policies/) -- MCPServerRegistration schema, on-premise registration flow, MCPVirtualServer CR, AuthPolicy (authn + authz), tool revocation
- **RHCL 1.4 Supported Configurations** -- [access.redhat.com/articles/7092611](https://access.redhat.com/articles/7092611) -- OCP version matrix (4.19-4.22), OSSM versions (3.3-3.4), cert-manager (1.19), Keycloak (26.6)
- **FastMCP 4.0.11 installed source code** -- OpenAPITool.run() base_url re-read per request, RequestDirector._build_url() URL joining, httpx2 imports
- **FastMCP OpenAPI docs** -- [gofastmcp.com/integrations/openapi](https://gofastmcp.com/integrations/openapi) -- from_openapi(), RouteMap, mcp_component_fn
- **Phase 2 codebase** -- openapi_to_mcp.py, allowlist_schema.py, mcp-telecom-deployment.yaml, configmap-backend-routing.yaml, test_configmap_watcher.py, test_allowlist_filtering.py

### Secondary (MEDIUM confidence)

- **OSSM + Gateway API Integration** -- [developers.redhat.com/articles/2025/12/09/integrate-openshift-gateway-api-openshift-service-mesh](https://developers.redhat.com/articles/2025/12/09/integrate-openshift-gateway-api-openshift-service-mesh) -- OSSM Operator Subscription, IstioCNI + Istio CR, GatewayClass, dual mesh concern
- **FastMCP 3-4 Migration** -- [dev.to/wolfejam/fastmcp-3-4-migration-the-breaking-changes-that-compile](https://dev.to/wolfejam/fastmcp-3-4-migration-the-breaking-changes-that-compile-k6p) -- httpx to httpx2 transition details
- **FastMCP SSRF Fix (CVE-2026-32871)** -- [github.com/PrefectHQ/fastmcp/security/advisories/GHSA-vv7q-7jx5-f767](https://github.com/PrefectHQ/fastmcp/security/advisories/GHSA-vv7q-7jx5-f767) -- RequestDirector URL building internals, path traversal fix in 3.2.0

### Tertiary (LOW confidence)

- RHCL 1.4 release notes for specific 1.4.1 bug fixes -- could not find a dedicated release notes page; the 1.4.0 deprecation notice is cited in the install guide but 1.4.1-specific fix details were not available [ASSUMED: 1.4.1 fixes the listed issues based on deprecation notice wording]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- FastMCP 4.0.11 verified, httpx2 verified, RHCL docs fetched
- Architecture (RHCL gateway): HIGH -- full MCPServerRegistration, MCPVirtualServer, AuthPolicy schemas extracted from docs
- Architecture (domain servers): HIGH -- conversion CLI proven in Phase 2, from_openapi() Swagger 2.0 support verified
- Pitfalls: HIGH -- all critical pitfalls verified against official sources or source code
- Base_url propagation: HIGH -- resolved definitively from installed source code + runtime test

**Research date:** 2026-10-04
**Valid until:** 2026-11-04 (stable -- RHCL 1.4 is current GA; FastMCP 4.x is settled post-2026-07-28 spec freeze)
