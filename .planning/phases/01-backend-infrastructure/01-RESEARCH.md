# Phase 1: Backend Infrastructure - Research

**Researched:** 2026-09-27
**Domain:** OpenShift backend deployment (Prism mock servers, NextGCore 5G core, routing ConfigMap)
**Confidence:** HIGH

## Summary

Phase 1 deploys mock and live backends on OpenShift so every fault-prediction API has a real HTTP endpoint for downstream MCP tools and SDG pipeline to call. The phase has three workstreams: (1) deploy four Prism mock server instances (TMF642, TMF628, TMF621, CAMARA DeviceLocation) from vendored OpenAPI specs, (2) validate and deploy NextGCore's NWDAF on OpenShift with nextgsim providing realistic analytics data, and (3) create a ConfigMap-based routing mechanism so future MCP servers can switch each API between mock and live backends without redeployment.

A critical discovery simplifies the NextGCore OpenShift porting: NextGCore uses **userspace SCTP (pure Rust over UDP)** by default, meaning kernel SCTP modules are NOT required. The `docker-compose.kernel-sctp.yml` is an optional overlay, not the default path. This eliminates the MachineConfig SCTP enablement step that PITFALLS.md Pitfall #8 flagged as a potential multi-week blocker. The primary SCC concern reduces to the UPF needing `NET_ADMIN` capability for TUN/TAP interface creation and IP forwarding. Other NFs should run under minimally elevated SCCs.

**Primary recommendation:** Deploy Prism mocks first (lowest risk, no dependencies), then validate NextGCore locally with Podman before investing OpenShift porting effort, and create the routing ConfigMap last as it depends on knowing the Service DNS names of deployed backends.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Deploy to a personal/dev OpenShift cluster, not a shared team or WG cluster.
- **D-02:** `oc` CLI access is not yet set up -- provisioning the cluster/login is in scope for Phase 1 setup work.
- **D-03:** User will provision a cluster with sufficient resources and admin-level access (not the free, quota-constrained Red Hat Developer Sandbox tier). This means SCC/quota limits are NOT expected to block NextGCore's deployment needs (custom SCCs, SCTP support).
- **D-04:** Use **Prism** (5.16.0) for mock backends, per ROADMAP.md/REQUIREMENTS.md and confirmed by prior research (`.planning/research/STACK.md`). Not Microcks.
- **D-05:** Deploy **one Prism instance per API spec** -- 4 separate Deployments/Services (`prism-tmf642`, `prism-tmf628`, `prism-tmf621`, `prism-camara`), each `prism mock -h 0.0.0.0 /specs/<spec>.yaml` on its own port.
- **D-06:** Vendor the OpenAPI spec files into this repo (e.g. under `backends/specs/`) rather than fetching them at build/deploy time.
- **D-07:** TMF628's Swagger 2.0 spec is mocked as-is -- no conversion to OAS 3.0 needed for mocking purposes.
- **D-08:** Mock responses should be dynamically generated from the schema (Prism's dynamic mode `--dynamic`), not static hand-authored examples.
- **D-09:** Verify mocks with an automated schema validation script/test. Prefer Prism's validation-proxy mode where it fits.
- **D-10:** NextGCore NWDAF: timebox-then-fallback strategy. If non-functional, fall back to mocking NWDAF via Prism.
- **D-11:** Timebox duration is at executing agent's discretion.
- **D-12:** Validate NextGCore locally with **Podman** first (not Docker), confirm NWDAF endpoints respond, then adapt for OpenShift.
- **D-13:** Set up **nextgsim** (UE registration + PDU session) as part of Phase 1 for realistic NWDAF analytics data.
- **D-14:** Routing granularity is **per-API** (tmf642, tmf628, tmf621, camara_devicelocation, nwdaf) -- not per tool.
- **D-15:** Plain Kubernetes ConfigMap holding mock/live base URLs per API. No routing proxy/gateway service.
- **D-16:** Build a throwaway test script to verify ConfigMap-based routing switching works.

### Claude's Discretion
- Exact timebox duration for NextGCore/NWDAF validation before falling back to mocking (D-11).
- Naming conventions for the OpenShift namespace/project, ConfigMap keys, and vendored spec directory structure.

### Deferred Ideas (OUT OF SCOPE)
- None -- discussion stayed within phase scope. Per-tool routing granularity and a routing-proxy service were explicitly deferred as premature.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BACK-01 | Deploy Prism mock backends on OpenShift for TMF642, TMF628, TMF621, and CAMARA APIs from their OpenAPI specs | Prism Docker image `stoplight/prism:5` verified on Docker Hub; custom Dockerfile pattern for baking in specs documented; per-API Deployment+Service+Route pattern researched; dynamic mode and error simulation via Prefer header confirmed |
| BACK-02 | Deploy NextGCore on OpenShift with working NWDAF endpoints for execution-verified analytics tool calls | NextGCore userspace SCTP confirmed (no kernel SCTP needed); Docker Compose structure documented; nextgsim E2E flow verified; k8s/ directory exists; UPF SCC requirements identified; NWDAF persistence limitations (issue #192) documented |
| BACK-03 | Configure backend routing via ConfigMap (swap between Prism mocks and live backends without code changes) | ConfigMap key/value shape confirmed from ARCHITECTURE.md; concrete verification script approach designed; environment variable injection pattern for future MCP consumers documented |
</phase_requirements>

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| TMF642/628/621 mock API responses | Backend Tier (Prism containers) | -- | Prism generates responses from OpenAPI spec schemas; no application logic needed |
| CAMARA DeviceLocation mock responses | Backend Tier (Prism container) | -- | Same Prism pattern as TMF mocks |
| NWDAF live analytics responses | Backend Tier (NextGCore 5G core) | Backend Tier (Prism fallback) | NextGCore provides TS 29.520 ONNX-backed analytics; Prism is fallback if NWDAF is non-functional |
| Backend routing (mock/live switching) | Infrastructure (ConfigMap) | -- | Pure Kubernetes-native configuration; consumed as environment variables by future MCP servers |
| Schema validation of mock responses | CI/Test scripts | -- | Standalone validation script, not a runtime service |
| UE/gNB simulation for realistic data | Backend Tier (nextgsim) | -- | Companion simulator generates network traffic that populates NWDAF analytics |

## Standard Stack

### Core

| Library/Tool | Version | Purpose | Why Standard | Confidence |
|-------------|---------|---------|--------------|------------|
| Prism (Stoplight) | 5.16.0 (npm) / 5.15.10 (Docker Hub `stoplight/prism:5`) | Auto-mock HTTP APIs from OpenAPI specs | Spec-driven, zero-config mocking; supports OAS 3.0 + Swagger 2.0; Docker-ready; single process per spec [VERIFIED: npm registry -- `npm view @stoplight/prism-cli version` returns 5.16.0] | HIGH |
| NextGCore | latest (git HEAD) | Live 5G SA core with NWDAF analytics | Only open-source 5G core with ONNX-backed NWDAF; pure Rust with userspace SCTP; Docker Compose deployment [CITED: github.com/NextgCoreLab/nextgcore] | HIGH |
| nextgsim | latest (git HEAD) | 5G UE/gNB simulator | Companion to NextGCore; drives UE registration + PDU session for realistic NWDAF data; pure Rust [CITED: github.com/NextgCoreLab/nextgsim] | HIGH |
| OpenShift Container Platform | 4.16+ | Container orchestration | Project constraint -- Red Hat platform required [CITED: .planning/PROJECT.md Constraints] | HIGH |

### Supporting

| Tool | Version | Purpose | When to Use |
|------|---------|---------|-------------|
| oc CLI | 4.18.16 | OpenShift cluster management | All cluster operations (deploy, SCC, ConfigMap) |
| Podman | 5.6.1 | Local container runtime | NextGCore local validation (D-12) |
| docker-compose | 5.0.2 | Compose file orchestration | Running NextGCore's compose files locally via Podman socket |
| Helm | 3.19.0 | Kubernetes package manager | Optional -- can use raw manifests for Phase 1 simplicity |
| Node.js | 25.x | Runtime (if building custom Prism image) | Prism custom Dockerfile |
| jq | 1.8.0 | JSON processing | Validation scripts, ConfigMap inspection |
| curl | 8.7.1 | HTTP testing | Health checks, validation scripts |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Custom Prism Dockerfile | `stoplight/prism:5` with ConfigMap volume mount | Custom image bakes in spec (immutable, no mount issues); ConfigMap mount is simpler but requires mount path configuration in Deployment |
| docker-compose for local NextGCore | podman-compose (Python package) | docker-compose v5.0.2 is already installed and has better Compose spec compatibility; podman-compose would need installation and has known networking gaps with custom bridges |
| Raw oc manifests | Helm chart | Raw manifests are simpler for Phase 1 (4 Prism Deployments + NextGCore); Helm adds templating overhead with no reuse benefit yet |

**Installation:**
```bash
# Prism CLI (for local testing / custom image build)
npm install -g @stoplight/prism-cli@5.16.0

# No new Python packages required for Phase 1
# oc, podman, helm, docker-compose already available on this machine
```

**Version verification:**
```bash
npm view @stoplight/prism-cli version   # Returns 5.16.0 [VERIFIED: npm registry]
oc version --client                      # Returns 4.18.16 [VERIFIED: local machine]
podman --version                         # Returns 5.6.1 [VERIFIED: local machine]
helm version --short                     # Returns v3.19.0 [VERIFIED: local machine]
```

## Package Legitimacy Audit

> slopcheck does not support npm packages (Python-only). Manual registry verification performed instead.

| Package | Registry | Age | Downloads | Source Repo | slopcheck | Disposition |
|---------|----------|-----|-----------|-------------|-----------|-------------|
| @stoplight/prism-cli | npm | 7+ yrs (created 2019-04-10) | 10M+ Docker pulls | github.com/stoplightio/prism | N/A (npm) | Approved -- manually verified: official Stoplight package, 7-year history, active maintenance, no postinstall script |
| NextGCore | git (source) | ~2 yrs | N/A (cloned from GitHub) | github.com/NextgCoreLab/nextgcore | N/A (git) | Approved -- AGPL-3.0 research core, sandbox use only per PROJECT.md |
| nextgsim | git (source) | ~2 yrs | N/A (cloned from GitHub) | github.com/NextgCoreLab/nextgsim | N/A (git) | Approved -- companion simulator, same org as NextGCore |

**Packages removed due to slopcheck [SLOP] verdict:** none
**Packages flagged as suspicious [SUS]:** none

## Architecture Patterns

### System Architecture Diagram

```
                    [Developer / CI]
                          |
                          | oc apply / helm install
                          v
              +------------------------+
              |   OpenShift Cluster    |
              |   (personal/dev)       |
              |                        |
              |  +------------------+  |
              |  | ConfigMap:       |  |
              |  | backend-routing  |  |
              |  | TMF642_BASE_URL  |--|----> prism-tmf642 Service
              |  | TMF628_BASE_URL  |--|----> prism-tmf628 Service
              |  | TMF621_BASE_URL  |--|----> prism-tmf621 Service
              |  | CAMARA_BASE_URL  |--|----> prism-camara Service
              |  | NWDAF_BASE_URL   |--|----> nextgcore-nwdaf Service (or prism-nwdaf fallback)
              |  +------------------+  |
              |                        |
              |  Backend Pods:         |
              |  +----------------+    |    +----------------+
              |  | prism-tmf642   |    |    | prism-tmf628   |
              |  | :4010          |    |    | :4010          |
              |  | TMF642 v5.0.1  |    |    | TMF628 v4.0.0  |
              |  | OAS 3.0 YAML   |    |    | Swagger 2.0    |
              |  +----------------+    |    +----------------+
              |                        |
              |  +----------------+    |    +----------------+
              |  | prism-tmf621   |    |    | prism-camara   |
              |  | :4010          |    |    | :4010          |
              |  | TMF621 v5.0.1  |    |    | CAMARA DL r3.2 |
              |  | OAS 3.0 YAML   |    |    | OAS 3.0 YAML   |
              |  +----------------+    |    +----------------+
              |                        |
              |  +----------------------------------+
              |  | NextGCore (multi-container pod)  |
              |  | AMF | SMF | UPF | NRF | NWDAF   |
              |  | + nextgsim (gNB + UE)            |
              |  | NWDAF endpoint: /nnwdaf-...      |
              |  +----------------------------------+
              |                        |
              +------------------------+
                          |
                     [Validation Script]
                     reads ConfigMap ->
                     curls each backend ->
                     validates responses
```

### Recommended Project Structure
```
backends/
  specs/                          # Vendored OpenAPI specs (D-06)
    tmf642_alarm_v5.0.1.oas.yaml
    tmf628_performance_v4.0.0.swagger.json
    tmf621_troubleticket_v5.0.1.oas.yaml
    camara_location_verification.yaml
    camara_location_retrieval.yaml
    nwdaf_analyticsinfo_rel16.yaml     # Rel-16 spec (matches NextGCore capability)
    nwdaf_eventssubscription_rel16.yaml
  prism/
    Dockerfile                    # Custom Prism image with baked-in spec
  nextgcore/
    docker-compose.local.yaml     # Podman-compatible compose for local validation
  openshift/
    namespace.yaml                # otel25-backends namespace
    prism-tmf642.yaml             # Deployment + Service + Route
    prism-tmf628.yaml
    prism-tmf621.yaml
    prism-camara.yaml
    nextgcore/
      scc-nextgcore-upf.yaml      # Custom SCC for UPF (NET_ADMIN)
      deployment-nextgcore.yaml   # Adapted from k8s/ directory
      service-nwdaf.yaml
    configmap-backend-routing.yaml
  scripts/
    validate-mocks.sh             # Automated schema validation (D-09)
    verify-routing.sh             # ConfigMap routing verification (D-16)
```

### Pattern 1: One Prism Instance Per API Spec

**What:** Each API specification gets its own Prism container, Deployment, Service, and (optionally) Route on OpenShift. The container image embeds the spec file.

**When to use:** Always for this project (D-05).

**Example Dockerfile:**
```dockerfile
# Source: Stoplight Prism Docker documentation
# https://hub.docker.com/r/stoplight/prism/
FROM stoplight/prism:5

# Copy the vendored spec into the image
COPY specs/tmf642_alarm_v5.0.1.oas.yaml /specs/api.yaml

# Run in dynamic mode, bind to all interfaces, production mode
ENV NODE_ENV=production
ENTRYPOINT ["node", "dist/index.js"]
CMD ["mock", "-h", "0.0.0.0", "-p", "4010", "--dynamic", "/specs/api.yaml"]
```

**Example OpenShift Deployment + Service:**
```yaml
# Source: Standard OpenShift Deployment pattern
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
            path: /alarm          # Any valid spec path returns mock data
            port: 4010
          initialDelaySeconds: 5
          periodSeconds: 10
        livenessProbe:
          httpGet:
            path: /alarm
            port: 4010
          initialDelaySeconds: 10
          periodSeconds: 30
---
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

### Pattern 2: ConfigMap-Based Backend Routing

**What:** A single ConfigMap holds the base URL for each API. Future MCP servers consume these as environment variables. Changing the ConfigMap and restarting the consumer pod switches backends.

**When to use:** Always (D-15).

**Example ConfigMap:**
```yaml
# Source: .planning/research/ARCHITECTURE.md Pattern 3
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
  NWDAF_BASE_URL: "http://nextgcore-nwdaf.otel25-backends.svc.cluster.local:8080"
```

**Verification script pattern (D-16):**
```bash
#!/usr/bin/env bash
# Read ConfigMap, call each backend, verify responses
set -euo pipefail

NAMESPACE="otel25-backends"
CM_NAME="backend-routing"

for KEY in TMF642_BASE_URL TMF628_BASE_URL TMF621_BASE_URL CAMARA_BASE_URL NWDAF_BASE_URL; do
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

### Pattern 3: Custom SCC for NextGCore UPF

**What:** Create a minimal custom SCC granting only the capabilities the UPF needs (NET_ADMIN for TUN/TAP interfaces, IP forwarding). Bind it to a dedicated service account. Never modify default SCCs.

**When to use:** When deploying NextGCore on OpenShift.

**Example:**
```yaml
# Source: Red Hat OpenShift SCC documentation
# https://docs.openshift.com/container-platform/4.18/authentication/managing-security-context-constraints.html
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
  type: RunAsAny          # UPF may need specific UID
seLinuxContext:
  type: MustRunAs
fsGroup:
  type: RunAsAny
supplementalGroups:
  type: RunAsAny
allowedCapabilities:
  - NET_ADMIN              # Required for TUN/TAP interface creation
  - NET_RAW                # May be needed for raw socket operations
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

```bash
# Bind SCC to service account
oc create -f scc-nextgcore-upf.yaml
oc create serviceaccount nextgcore-upf -n otel25-backends
oc adm policy add-scc-to-user nextgcore-upf -z nextgcore-upf -n otel25-backends
```

### Anti-Patterns to Avoid

- **Modifying default SCCs:** OpenShift resets default SCCs on upgrade. Always create custom SCCs. [CITED: docs.openshift.com/container-platform/4.18/authentication/managing-security-context-constraints.html]
- **Embedding backend URLs in code:** ARCHITECTURE.md Anti-Pattern 5. Use ConfigMap environment variables. The same code must work against Prism and live backends.
- **Deploying Prism without `-h 0.0.0.0`:** Prism defaults to localhost (127.0.0.1). Without binding to 0.0.0.0, the mock is unreachable from outside the container. [CITED: docs.stoplight.io/docs/prism/f51bcc80a02db-installation]
- **Using Prism without `NODE_ENV=production` or `-m` flag:** Processing logs slows Prism significantly. In container deployments, always run in production mode. [CITED: docs.stoplight.io/docs/prism/f51bcc80a02db-installation]
- **Assuming kernel SCTP is needed for NextGCore:** NextGCore uses userspace SCTP (pure Rust over UDP) by default. The `docker-compose.kernel-sctp.yml` is an optional overlay. Do NOT spend time enabling SCTP via MachineConfig unless explicitly using the kernel-SCTP overlay. [CITED: github.com/NextgCoreLab/nextgcore -- "Userspace SCTP -- pure Rust SCTP implementation over UDP, no kernel SCTP required"]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Mock API responses from OpenAPI specs | Custom mock server with hand-written stubs | Prism `--dynamic` mode | TMF specs have 50+ operations total; hand-stubbing is impractical. Prism reads the spec and generates conforming responses automatically |
| 5G UE registration / PDU session | Custom protocol simulators | nextgsim (companion to NextGCore) | NGAP/NAS/RRC protocols are enormously complex; nextgsim implements them in Rust |
| Container orchestration on OpenShift | Shell scripts managing containers | OpenShift Deployments + Services | Native health checking, restart policies, rolling updates, DNS-based service discovery |
| Backend URL management | Environment-variable scripts or .env files | Kubernetes ConfigMap | Native `oc edit configmap`, consumed as env vars, auditable, versionable |

**Key insight:** Phase 1 involves zero custom application code. Everything is container deployment, configuration, and validation scripts. The risk is operational (getting containers running on OpenShift with correct networking and permissions), not algorithmic.

## Common Pitfalls

### Pitfall 1: Prism Docker Image Version Lag

**What goes wrong:** STACK.md specifies Prism 5.16.0, but the Docker Hub `stoplight/prism:5` tag currently points to 5.15.10. Building a custom image with `npm install -g @stoplight/prism-cli@5.16.0` gets the npm version, while using the pre-built Docker image gets 5.15.10.
**Why it happens:** Docker Hub image publishing lags npm releases. v5.16.0 was released on npm 2026-07-17 but Docker Hub still shows 5.15.10 as latest.
**How to avoid:** Build a custom Docker image using `FROM node:24-slim` + `npm install -g @stoplight/prism-cli@5.16.0` for exact version pinning. Or use `stoplight/prism:5` (5.15.10) which is functionally equivalent for mocking purposes -- v5.16.0 changes were dependency bumps and analytics, not mocking features.
**Warning signs:** Check `docker inspect stoplight/prism:5` for version labels before deploying.

### Pitfall 2: NextGCore NWDAF Persistence (Issue #192)

**What goes wrong:** NWDAF analytics subscriptions are memory-only. A container restart silently drops all subscriptions with no termination signal to consumers. After a pod restart on OpenShift, NWDAF analytics queries that depended on subscriptions will return empty/default data.
**Why it happens:** NextGCore stores subscriptions in in-memory maps with no durable store and no reload at boot. This is a known design limitation (issue #192). [CITED: github.com/NextgCoreLab/nextgcore/issues/192]
**How to avoid:** For Phase 1 validation, use one-shot analytics queries (GET /analytics with event-id) rather than subscription-based flows. If subscriptions are needed, re-establish them after any restart. Plan for the timebox-then-fallback strategy (D-10).
**Warning signs:** NWDAF returns empty analytics results after any pod disruption.

### Pitfall 3: Podman Compose Networking Differences

**What goes wrong:** NextGCore's Docker Compose files define custom bridge networks (172.23.0.0/24) with specific container IP assignments. `podman-compose` uses pod-based networking where all containers share a network namespace, breaking the explicit IP assignments NextGCore expects.
**Why it happens:** Podman Compose and Docker Compose have fundamentally different networking models. Docker Compose creates bridge networks; podman-compose groups containers in a pod with shared localhost. [CITED: redhat.com/en/blog/podman-compose-docker-compose]
**How to avoid:** Use the standalone `docker-compose` binary (v5.0.2, already installed) against Podman's Docker-compatible socket. Enable the socket: `systemctl --user enable --now podman.socket`, set `DOCKER_HOST=unix://$XDG_RUNTIME_DIR/podman/podman.sock`, then run `docker-compose -f docker-compose.yml up -d`. This preserves Docker Compose's bridge networking while using Podman as the runtime.
**Warning signs:** Containers cannot reach each other by service name or IP; AMF logs show connection refused to NRF/SMF.

### Pitfall 4: Prism Health Check Path Selection

**What goes wrong:** Prism has no dedicated `/health` endpoint. OpenShift readiness/liveness probes need a valid HTTP path. Using a random path that doesn't match the spec returns 404 (mock mode still returns spec-defined error responses). Using a valid GET endpoint works but returns dynamic mock data, which is fine for health checking.
**Why it happens:** Prism is a mock server, not an application server. It responds to spec-defined paths only.
**How to avoid:** Choose a simple GET endpoint from each spec as the health check path. Examples: `/alarm` for TMF642, `/measurementCollectionJob` for TMF628, `/troubleTicket` for TMF621, `/verify` for CAMARA (may need POST body -- prefer a GET path). Check that the chosen path exists in the spec and returns 200 for GET requests.
**Warning signs:** Probes returning 404/405, causing pods to be marked not-ready.

### Pitfall 5: TMF628 Swagger 2.0 Spec with Prism

**What goes wrong:** TMF628 is the only spec in Swagger 2.0 format (JSON). Prism supports Swagger 2.0 (D-07 confirms this), but some advanced schema features (discriminators, nullable fields) may behave differently between Swagger 2.0 and OAS 3.0 parsing.
**Why it happens:** Swagger 2.0 and OAS 3.0 have different schema capabilities. Prism internally converts Swagger 2.0 to OAS 3.0 for processing.
**How to avoid:** Test the TMF628 mock locally before deploying to OpenShift. Run `prism mock --dynamic TMF628-Performance-v4.0.0.swagger.json` and curl several endpoints. If Prism fails to parse or produces errors, check for circular references (Prism refuses to mock documents with circular $refs).
**Warning signs:** Prism startup errors mentioning "circular reference" or "cannot resolve $ref".

## Code Examples

### Local Prism Mock Testing (pre-OpenShift)
```bash
# Source: Stoplight Prism CLI docs
# https://docs.stoplight.io/docs/prism/beeaad4dc0227-prism-cli

# Start TMF642 mock locally with dynamic responses
npx @stoplight/prism-cli mock --dynamic -h 0.0.0.0 -p 4010 \
  backends/specs/tmf642_alarm_v5.0.1.oas.yaml

# Test basic GET endpoint
curl -s http://localhost:4010/alarm | jq .

# Test with dynamic response header (explicit dynamic for specific request)
curl -s http://localhost:4010/alarm -H "Prefer: dynamic=true" | jq .

# Test error simulation (status code must be defined in spec)
curl -s http://localhost:4010/alarm/nonexistent -H "Prefer: code=404" | jq .

# Test 500 error simulation
curl -s http://localhost:4010/alarm -H "Prefer: code=500" | jq .
```

### NextGCore Local Validation with Podman (D-12)
```bash
# Source: NextGCore README / Docker setup instructions
# https://github.com/NextgCoreLab/nextgcore

# Step 1: Enable Podman Docker-compatible socket (macOS)
# On macOS with Podman Desktop, the socket is typically already available
# On Linux: systemctl --user enable --now podman.socket

# Step 2: Clone both repos
git clone https://github.com/NextgCoreLab/nextgcore.git /tmp/nextgcore
git clone https://github.com/NextgCoreLab/nextgsim.git /tmp/nextgsim

# Step 3: Start the full E2E stack (22-NF 5GC + nextgsim gNB/UE)
cd /tmp/nextgcore/docker/rust
docker-compose -f docker-compose.yml up -d

# Step 4: Verify UE registration and PDU session (D-13)
sleep 30  # Allow NFs to start and register
docker-compose logs nextgsim-ue 2>&1 | grep -E "UE is now REGISTERED|is now ACTIVE"
# Expected output:
#   Registration Accept: UE is now REGISTERED
#   PDU session 1 is now ACTIVE (IPv4: 10.45.0.2)

# Step 5: Test NWDAF analytics endpoint
# The NWDAF endpoint should be accessible from within the Docker network
docker-compose exec nextgcore-amf curl -s \
  http://nextgcore-nwdaf:8080/nnwdaf-analyticsinfo/v1/analytics?event-id=LOAD_LEVEL_INFORMATION

# Step 6: If NWDAF responds with real data, proceed to OpenShift porting
# If NWDAF returns errors/empty, trigger timebox-then-fallback (D-10)
```

### Prism Validation-Proxy Mode (D-09 option)
```bash
# Source: Prism validation proxy docs
# https://github.com/stoplightio/prism/blob/master/docs/guides/03-validation-proxy.md

# Run Prism as a validation proxy between a test client and the mock Prism instance
# This validates that the mock responses conform to the spec
prism proxy backends/specs/tmf642_alarm_v5.0.1.oas.yaml \
  http://prism-tmf642.otel25-backends.svc.cluster.local:4010 \
  --errors -h 0.0.0.0 -p 5010

# Violations are reported:
# 1. On stderr (with --errors flag, non-conformant traffic is rejected)
# 2. In the sl-violations response header (JSON object with all violations)

# Test through the proxy:
curl -s -D - http://localhost:5010/alarm 2>&1 | grep -i sl-violations
# Empty sl-violations header = response conforms to spec
```

### Standalone Validation Script (D-09 alternative -- recommended)
```bash
#!/usr/bin/env bash
# validate-mocks.sh -- Verify Prism mock responses match OpenAPI specs
# Preferred over validation-proxy for Phase 1 because:
# - Prism validating its own output is circular (will always pass)
# - A standalone script with explicit assertions is more meaningful
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
    # Verify response is valid JSON
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

## OpenAPI Spec Vendoring Details

Concrete files to download and vendor into `backends/specs/` (D-06):

| Spec | Source URL | Format | File to Save As |
|------|-----------|--------|-----------------|
| TMF642 Alarm v5.0.1 | `https://raw.githubusercontent.com/tmforum-apis/TMF642_AlarmManagement/main/TMF642_Alarm_v5.0.1.oas.yaml` | OAS 3.0 YAML | `tmf642_alarm_v5.0.1.oas.yaml` |
| TMF628 Performance v4.0.0 | `https://raw.githubusercontent.com/tmforum-apis/TMF628_Performance/main/TMF628-Performance-v4.0.0.swagger.json` | Swagger 2.0 JSON | `tmf628_performance_v4.0.0.swagger.json` |
| TMF621 Trouble Ticket v5.0.1 | `https://raw.githubusercontent.com/tmforum-apis/TMF621_TroubleTicket/main/TMF621-Trouble_Ticket-v5.0.1.oas.yaml` | OAS 3.0 YAML | `tmf621_troubleticket_v5.0.1.oas.yaml` |
| CAMARA Location Verification | `https://raw.githubusercontent.com/camaraproject/DeviceLocation/r3.2/code/API_definitions/location-verification.yaml` | OAS 3.0 YAML | `camara_location_verification.yaml` |
| CAMARA Location Retrieval | `https://raw.githubusercontent.com/camaraproject/DeviceLocation/r3.2/code/API_definitions/location-retrieval.yaml` | OAS 3.0 YAML | `camara_location_retrieval.yaml` |
| NWDAF AnalyticsInfo (Rel-16) | `https://raw.githubusercontent.com/jdegre/5GC_APIs/Rel-16/TS29520_Nnwdaf_AnalyticsInfo.yaml` | OAS 3.0 YAML | `nwdaf_analyticsinfo_rel16.yaml` |
| NWDAF EventsSubscription (Rel-16) | `https://raw.githubusercontent.com/jdegre/5GC_APIs/Rel-16/TS29520_Nnwdaf_EventsSubscription.yaml` | OAS 3.0 YAML | `nwdaf_eventssubscription_rel16.yaml` |

**Why Rel-16 for NWDAF, not Rel-18:** NextGCore's NWDAF is derived from Open5GS which implements Rel-16 at best. PITFALLS.md Pitfall #13 warns that using Rel-18 specs creates a release mismatch where MCP tools reference endpoints NextGCore does not serve. Rel-16 specs are frozen and match what NextGCore can realistically support. [CITED: PITFALLS.md Pitfall #13, arxiv.org/html/2601.01838v1]

**CAMARA note:** The CAMARA DeviceLocation repo has two separate spec files (location-verification.yaml, location-retrieval.yaml). For the Prism mock, either serve both from a single Prism instance (if they share a base path) or use two instances. Since D-05 specifies "one Prism instance per API spec" and the two CAMARA specs are for the same API family, a single `prism-camara` instance serving one combined spec is simpler. If Prism cannot serve two specs, pick the more relevant one (location-verification, used by `camara_verify_location` tool) and add the other later.

## NextGCore OpenShift Porting: Detailed Findings

### Key Discovery: No Kernel SCTP Required

NextGCore uses a **pure Rust userspace SCTP implementation over UDP**. This is a feature listed in the project's README:

> "Userspace SCTP -- pure Rust SCTP implementation over UDP, no kernel SCTP required" [CITED: github.com/NextgCoreLab/nextgcore]

This means:
- **MachineConfig for SCTP is NOT needed** (eliminates the multi-week blocker from PITFALLS.md Pitfall #8)
- The `docker-compose.kernel-sctp.yml` overlay is for optional native kernel SCTP and should NOT be used for OpenShift deployment
- NGAP signaling (AMF <-> gNB) works over userspace SCTP/UDP without kernel module support
- This works on any OpenShift cluster without node-level configuration changes

### UPF-Specific Requirements

The UPF needs elevated permissions because it:
1. Creates TUN/TAP interfaces for user-plane data forwarding
2. Enables IP forwarding (`sysctl net.ipv4.ip_forward=1`)
3. Handles GTP-U tunneling

These require a custom SCC with `NET_ADMIN` (and possibly `NET_RAW`) capabilities. See Pattern 3 above for the SCC definition.

### Other NFs (AMF, SMF, NRF, NWDAF, etc.)

All other NFs are pure Rust userspace processes. They should run under the default `restricted-v2` SCC or a minimally elevated SCC. Test with `restricted-v2` first; if it fails, create a minimal custom SCC granting only the specific capability needed.

### Docker Compose to OpenShift Conversion

NextGCore provides:
- `docker-compose.yml` in `docker/rust/` -- Full 22-NF stack with nextgsim
- A `k8s/` directory at the repo root (contents not fully documented; need to inspect at execution time)

The conversion requires:
1. **Each NF binary -> separate container** in a multi-container Pod (or separate Pods for NFs that can scale independently)
2. **Docker network 172.23.0.0/24 -> OpenShift Service DNS names** (replace hardcoded IPs with service discovery)
3. **Docker volume mounts for configs -> ConfigMap mounts** (NextGCore configs from `configs/` directory)
4. **Docker Compose `depends_on` -> init containers or startup probes** (ensure NRF starts before other NFs register)

### Recommended OpenShift Deployment Topology for NextGCore

```
Pod: nextgcore-core (StatefulSet, replicas: 1)
  Containers:
    - nextgcore-nrfd        # Must start first (NF registry)
    - nextgcore-amfd        # Registers with NRF
    - nextgcore-smfd        # Session management
    - nextgcore-udmd        # Subscriber data
    - nextgcore-udrd        # Data repository
    - nextgcore-ausfd       # Authentication
    - nextgcore-pcfd        # Policy
    - nextgcore-nwdafd      # NWDAF analytics (the target NF)
    ... (other NFs as needed)

Pod: nextgcore-upf (Deployment, replicas: 1)
  ServiceAccount: nextgcore-upf (bound to custom SCC)
  Containers:
    - nextgcore-upfd        # Needs NET_ADMIN SCC

Pod: nextgsim (Deployment, replicas: 1)
  Containers:
    - nextgsim-gnb          # gNB simulator
    - nextgsim-ue           # UE simulator
```

**Alternative (simpler for Phase 1):** Run all NextGCore NFs in a single Pod with shared networking. This mirrors the Docker Compose topology and avoids needing to figure out inter-pod service discovery for each NF. Use init containers to enforce startup order (NRF first).

## Schema Validation Strategy (D-09)

### Recommendation: Standalone validation script, NOT Prism validation-proxy

**Rationale:** Prism's validation-proxy mode (`prism proxy spec.yaml http://mock:4010 --errors`) is designed to validate a *real* backend against a spec. When the "real" backend IS Prism itself, this is circular -- Prism generates responses from the spec, and validation-proxy validates them against the same spec. This will always pass (by construction), making it a tautological test.

A meaningful test for Phase 1 is:

1. **HTTP reachability:** Can each Prism mock receive requests and return 2xx responses?
2. **Response structure:** Are responses valid JSON matching the expected shape?
3. **Dynamic variation:** Does `--dynamic` mode produce varied (not identical) responses across calls?
4. **Error simulation:** Does `Prefer: code=4xx/5xx` return the expected error codes?

The validation script (see Code Examples above) tests these properties directly without the circular dependency.

**However, Prism validation-proxy IS valuable for Phase 2+** when testing real MCP server requests against the spec. At that point, MCP server -> Prism proxy -> Prism mock is non-circular because the *requests* come from real code (MCP tool implementations), and the proxy validates that those requests conform to the spec.

### Prism Error Simulation for Future SDG

Prism supports error simulation via the `Prefer` header. This is relevant for PITFALLS.md Pitfall #9 (happy-path-only training data), though not Phase 1's scope:
```bash
curl http://prism-tmf642:4010/alarm -H "Prefer: code=404"   # Not found
curl http://prism-tmf642:4010/alarm -H "Prefer: code=500"   # Server error
```
The status code must be defined in the OpenAPI spec's responses section. [CITED: Prism CLI docs -- docs.stoplight.io/docs/prism/beeaad4dc0227-prism-cli]

## OpenShift Cluster Prerequisites (D-03)

### What "admin-level access" Concretely Requires

| Capability | Why Needed | oc Command |
|------------|-----------|------------|
| Create namespace/project | Isolate Phase 1 resources | `oc new-project otel25-backends` |
| Create custom SCC | UPF needs NET_ADMIN | `oc create -f scc-nextgcore-upf.yaml` (requires cluster-admin) |
| Bind SCC to ServiceAccount | Grant SCC to UPF SA | `oc adm policy add-scc-to-user nextgcore-upf -z nextgcore-upf` (requires cluster-admin) |
| Push images to internal registry | Deploy custom Prism images | `oc registry login`, `podman push` to internal registry |
| Create Deployments, Services, Routes, ConfigMaps | Standard app deployment | Standard developer-level access suffices |
| View pod logs and exec into pods | Debugging | Standard developer-level access |

**Minimum required role:** `cluster-admin` for SCC creation and SCC-to-SA binding. Everything else works with `admin` role on the namespace. [CITED: docs.openshift.com/container-platform/4.18/authentication/managing-security-context-constraints.html]

**If NOT deploying NextGCore on OpenShift** (e.g., NWDAF falls back to Prism mock per D-10), cluster-admin is not needed at all. Prism containers run under the default `restricted-v2` SCC without elevation.

### Cluster Login Setup (D-02)

Since `oc` is already installed (v4.18.16), the setup is:
```bash
# Login to the provisioned cluster
oc login --server=https://<cluster-api>:6443 --token=<token>
# Or: oc login --server=https://<cluster-api>:6443 -u <user> -p <password>

# Verify cluster access
oc whoami
oc get nodes
oc auth can-i create securitycontextconstraints  # Should return "yes" for cluster-admin
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Kernel SCTP required for 5G cores on OpenShift | NextGCore uses userspace SCTP over UDP | NextGCore current release | Eliminates MachineConfig SCTP enablement; deploys on any OpenShift cluster |
| Prism v4 Docker image tags | Prism v5 image tags (`stoplight/prism:5`) | Prism v5.0.0 release | Must use `:5` tag not `:4`; v5 is actively maintained |
| Manual mock server stubs per endpoint | Prism `--dynamic` mode with json-schema-faker | Prism feature (stable) | Auto-generates varied responses from schema; no hand-authoring needed for Phase 1 |
| Docker-only container workflows | Podman + docker-compose via socket | Podman 3.0+ | Use `docker-compose` against Podman socket for best compatibility with existing compose files |

**Deprecated/outdated:**
- Prism `:4` Docker tag -- still works but v5 is current. STACK.md references 5.16.0 which is correct.
- `podman-compose` (Python package) -- less compatible than using `docker-compose` binary against Podman socket. Avoid unless docker-compose is unavailable.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | NextGCore's `k8s/` directory contains usable Kubernetes manifests that can be adapted for OpenShift | NextGCore OpenShift Porting | If empty or unmaintained, must write OpenShift manifests from scratch from docker-compose.yml (adds ~0.5 day effort) |
| A2 | NextGCore UPF requires only NET_ADMIN (not full privileged) for TUN/TAP creation | Custom SCC pattern | If UPF needs privileged SCC, security posture is worse; may need discussion with cluster admin |
| A3 | CAMARA location-verification.yaml and location-retrieval.yaml can be served by a single Prism instance | Spec vendoring | If Prism cannot serve two specs simultaneously, need two instances or merge specs manually |
| A4 | NWDAF Rel-16 AnalyticsInfo endpoint path is `/nnwdaf-analyticsinfo/v1/analytics` with `event-id` query param | Code examples | If NextGCore uses a different path convention, curl commands need adjustment |
| A5 | docker-compose v5.0.2 binary works correctly with Podman socket for NextGCore's compose files | Podman Compose pitfall | If networking breaks due to Podman/Docker bridge differences, may need to install podman-compose or use `podman play kube` instead |
| A6 | Prism health check works by hitting any GET endpoint defined in the spec | Pitfall 4 | If some GET endpoints require query parameters or return 4xx without them, need to find a better health check path |

## Open Questions (RESOLVED)

1. **NextGCore k8s/ directory contents**
   - What we know: The directory exists at the repo root
   - What's unclear: Whether it contains complete Kubernetes manifests, partial templates, or is empty/stale
   - Recommendation: Inspect during execution; if unusable, generate manifests from docker-compose.yml using `kompose convert` or write manually
   - **RESOLVED:** Delegated to 01-02 Task 1 (local Podman investigation clones the repo and inspects `k8s/` directly) and, if NWDAF is a go, 01-04 (OpenShift porting task reads the actual directory contents before writing manifests). Not a planning-time blocker — resolved empirically at execution time.

2. **NWDAF analytics endpoint behavior after nextgsim registration**
   - What we know: nextgsim does UE registration + PDU session; NWDAF is listed as one of the 22 NFs
   - What's unclear: Whether NWDAF returns actual analytics (LOAD_LEVEL_INFORMATION, ABNORMAL_BEHAVIOUR) after UE registration, or whether it requires additional configuration/data ingestion
   - Recommendation: This is the core validation step (D-12). Must be tested empirically with Podman before committing to OpenShift porting
   - **RESOLVED:** Delegated to 01-02 Task 1's empirical Podman test, which produces the go/no-go decision in `01-02-SUMMARY.md` that 01-04 branches on (NextGCore deployment vs. Prism fallback per D-10).

3. **CAMARA spec single-instance serving**
   - What we know: CAMARA DeviceLocation has two separate spec files (verification + retrieval)
   - What's unclear: Whether Prism can mock from two spec files in a single instance
   - Recommendation: Test locally with `prism mock --dynamic location-verification.yaml`. If both specs share the same base path, consider merging them. If not, deploy two Prism instances or pick the primary spec.
   - **RESOLVED:** Delegated to 01-01 (spec vendoring) and 01-03 (Prism Deployment authoring) — the executor inspects both vendored specs at execution time and picks single-vs-dual-instance serving per this recommendation, captured in those tasks' `read_first`/`action` fields.

4. **Prism readiness probe path for each API**
   - What we know: Prism has no `/health` endpoint; must use a spec-defined path
   - What's unclear: Whether TMF628 and CAMARA specs have GET endpoints that return 200 without mandatory query parameters
   - Recommendation: Inspect each vendored spec at execution time; find a simple GET path per spec for probes
   - **RESOLVED:** Delegated to 01-03 — each Prism Deployment's readiness/liveness probe path is determined by inspecting its vendored spec when authoring that Deployment's manifest, per this recommendation.

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| oc CLI | All OpenShift operations | Yes | 4.18.16 | -- |
| Podman | NextGCore local validation (D-12) | Yes | 5.6.1 | -- |
| docker-compose | Running NextGCore compose files | Yes | 5.0.2 | Install podman-compose via pip |
| Helm | Optional chart packaging | Yes | 3.19.0 | Use raw oc manifests |
| Node.js / npm | Building custom Prism image, local testing | Yes | 25.2.1 / 11.6.2 | -- |
| curl | Validation scripts | Yes | 8.7.1 | -- |
| jq | JSON processing in scripts | Yes | 1.8.0 | -- |
| Python 3 | Optional validation scripts | Yes | 3.14.6 | Bash scripts suffice |
| OpenShift cluster | Deployment target | No (D-02: not yet provisioned) | -- | Must be provisioned as first task |
| podman-compose | Alternative compose runner | No | -- | Use docker-compose v5.0.2 with Podman socket |
| Rust toolchain | Building NextGCore from source (if needed) | Not checked | -- | Use pre-built Docker images |

**Missing dependencies with no fallback:**
- OpenShift cluster (D-02 states provisioning is in scope for Phase 1)

**Missing dependencies with fallback:**
- podman-compose: not installed, but docker-compose v5.0.2 is available and is the better option for Podman compatibility

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | Bash scripts (curl + jq) for HTTP validation |
| Config file | None -- scripts are self-contained |
| Quick run command | `bash backends/scripts/validate-mocks.sh` |
| Full suite command | `bash backends/scripts/validate-mocks.sh && bash backends/scripts/verify-routing.sh` |

### Phase Requirements to Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BACK-01 | Prism mock servers return valid HTTP responses matching OpenAPI spec schemas | smoke + integration | `bash backends/scripts/validate-mocks.sh` | No -- Wave 0 |
| BACK-02 | NextGCore NWDAF endpoints respond to TS 29.520 analytics requests | smoke | `curl $NWDAF_BASE_URL/nnwdaf-analyticsinfo/v1/analytics?event-id=LOAD_LEVEL_INFORMATION` | No -- Wave 0 |
| BACK-03 | ConfigMap routing switches backends without redeploying | integration | `bash backends/scripts/verify-routing.sh` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `bash backends/scripts/validate-mocks.sh` (quick -- curls 4 endpoints)
- **Per wave merge:** Full suite (validate-mocks + verify-routing + NWDAF check)
- **Phase gate:** All scripts green; all Prism pods healthy; ConfigMap routing verified

### Wave 0 Gaps
- [ ] `backends/scripts/validate-mocks.sh` -- covers BACK-01
- [ ] `backends/scripts/verify-routing.sh` -- covers BACK-03
- [ ] `backends/scripts/check-nwdaf.sh` -- covers BACK-02 (or manual curl if NWDAF not deployed)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | No | Prism mocks and NextGCore dev deployment do not require auth for Phase 1 |
| V3 Session Management | No | No user sessions in backend infrastructure |
| V4 Access Control | Yes (OpenShift) | Custom SCCs with least privilege; dedicated ServiceAccounts per workload |
| V5 Input Validation | No (deferred) | Prism validates requests against OpenAPI spec by design; no custom validation code in Phase 1 |
| V6 Cryptography | No | No secrets or crypto operations in Phase 1 backends |

### Known Threat Patterns for Phase 1 Stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Over-privileged container (UPF with excessive caps) | Elevation of Privilege | Custom SCC with minimum capabilities (NET_ADMIN only); never use `privileged: true` |
| Exposed mock endpoints outside cluster | Information Disclosure | ClusterIP Services (no external Routes for mocks); Routes only if explicitly needed for debugging |
| Stale ConfigMap pointing to non-existent service | Denial of Service | Validation script checks all URLs before marking deployment complete |
| NWDAF subscription loss on restart | Denial of Service | Document as known limitation; use one-shot queries not subscriptions for Phase 1 |

## Project Constraints (from CLAUDE.md)

CLAUDE.md does not exist in this project repository. No project-specific directives to enforce.

Global user instructions (from ~/.claude/CLAUDE.md):
- Never push `.gitignore` files to GitHub repos -- keep them local only
- Never push blog drafts or personal notes to GitHub repos
- When staging files, always review what's being added -- prefer explicit file paths over `git add .`

## Sources

### Primary (HIGH confidence)
- [Stoplight Prism CLI docs](https://docs.stoplight.io/docs/prism/beeaad4dc0227-prism-cli) -- CLI flags, `-h 0.0.0.0`, `--dynamic`, `NODE_ENV=production`
- [Stoplight Prism validation proxy docs](https://github.com/stoplightio/prism/blob/master/docs/guides/03-validation-proxy.md) -- proxy command syntax, `--errors` flag, `sl-violations` header
- [Stoplight Prism Docker Hub](https://hub.docker.com/r/stoplight/prism/) -- image tags, v5 tag points to 5.15.10
- [Prism GitHub releases](https://github.com/stoplightio/prism/releases) -- v5.16.0 released 2026-07-17 (npm only, Docker Hub lag)
- [npm: @stoplight/prism-cli](https://www.npmjs.com/package/@stoplight/prism-cli) -- version 5.16.0 verified via `npm view`
- [NextGCore GitHub](https://github.com/NextgCoreLab/nextgcore) -- userspace SCTP, Docker Compose files, k8s/ directory, 22-NF stack
- [nextgsim GitHub](https://github.com/NextgCoreLab/nextgsim) -- UE/gNB simulator, E2E test flow, log verification
- [NextGCore issue #192](https://github.com/NextgCoreLab/nextgcore/issues/192) -- NWDAF subscriptions memory-only
- [NextGCore nextgsim issue #39](https://github.com/NextgCoreLab/nextgsim/issues/39) -- NWDAF handover trigger is no-op
- [OpenShift SCC docs (4.18)](https://docs.openshift.com/container-platform/4.18/authentication/managing-security-context-constraints.html) -- custom SCC creation, never modify defaults
- [OpenShift SCTP MachineConfig (4.9)](https://docs.openshift.com/container-platform/4.9/networking/using-sctp.html) -- SCTP enablement procedure (confirmed NOT needed for NextGCore default)
- [TMF642 GitHub repo](https://github.com/tmforum-apis/TMF642_AlarmManagement) -- v5.0.1 OAS YAML + v4.0.0 Swagger JSON, Apache 2.0
- [TMF628 GitHub repo](https://github.com/tmforum-apis/TMF628_Performance) -- v4.0.0 Swagger 2.0 JSON only, Apache 2.0
- [TMF621 GitHub repo](https://github.com/tmforum-apis/TMF621_TroubleTicket) -- v5.0.1 OAS YAML + v4.0.0 Swagger JSON, Apache 2.0
- [CAMARA DeviceLocation GitHub](https://github.com/camaraproject/DeviceLocation) -- r3.2 release, location-verification.yaml + location-retrieval.yaml, Apache 2.0
- [jdegre/5GC_APIs Rel-16](https://github.com/jdegre/5GC_APIs/tree/Rel-16) -- TS29520 NWDAF AnalyticsInfo + EventsSubscription YAML, 3GPP spec

### Secondary (MEDIUM confidence)
- [Open5GS on OpenShift (Medium)](https://medium.com/@anil.sonmez/open5gs-on-openshift-container-platform-c92e72dd4738) -- SCC patterns for 5G core, SCTP requirements
- [Podman Compose vs Docker Compose (Red Hat blog)](https://www.redhat.com/en/blog/podman-compose-docker-compose) -- networking model differences
- [Enhanced Open-Source NWDAF (arxiv)](https://arxiv.org/html/2601.01838v1) -- NWDAF release lag, open-source implementation gaps
- [Prism error simulation (Zenn)](https://zenn.dev/tonbi_attack/articles/fbd19e82b34eef?locale=en) -- Prefer header code=xxx usage

### Tertiary (LOW confidence)
- [Prism validation-proxy schema bug (issue #2442)](https://github.com/stoplightio/prism/issues/2442) -- invalid schemas may cause proxy to always pass; relevance depends on TMF spec quality

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- Prism version verified on npm, NextGCore features confirmed from GitHub, all tools checked on local machine
- Architecture: HIGH -- patterns derived from official OpenShift docs and verified prior research (ARCHITECTURE.md)
- Pitfalls: HIGH -- grounded in verified GitHub issues (#192, #39), official Prism docs, and confirmed version discrepancies

**Research date:** 2026-09-27
**Valid until:** 2026-10-27 (stable tools, no fast-moving dependencies in Phase 1)
