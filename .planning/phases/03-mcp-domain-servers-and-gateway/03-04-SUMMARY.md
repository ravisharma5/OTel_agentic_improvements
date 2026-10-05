---
phase: 03-mcp-domain-servers-and-gateway
plan: 04
subsystem: gateway-infrastructure
tags: [rhcl, mcp-gateway, ossm, keycloak, istio, openshift, gateway-api]
dependency_graph:
  requires: []
  provides:
    - otel25-gateway namespace with RHCL MCP Gateway infrastructure
    - OSSM 3.4.2 Istio control plane (IstioCNI + Istio CRs)
    - cert-manager operator (pre-existing v1.20.1)
    - Keycloak instance with mcp realm and mcp-gateway client
    - Gateway + MCPGatewayExtension ready for backend registration
    - keycloak-client-secret-mcp-gateway k8s Secret
  affects:
    - Plans 05 and 06 depend on the gateway and Keycloak being Ready
tech_stack:
  added:
    - OSSM 3.4.2 (servicemeshoperator3)
    - IstioCNI + Istio control plane (sailoperator.io/v1)
    - Red Hat build of Keycloak 26.6.7-opr.1 (rhbk-operator)
    - MCP Gateway Operator 0.7.1 (RHCL 1.4 Tech Preview)
    - Gateway API (gateway.networking.k8s.io/v1)
  patterns:
    - OLM Subscription for operator installation
    - Istio GatewayClass (not openshift-default) for Gateway API
    - Dual-listener Gateway (mcp for external, mcps for internal routing)
    - OpenShift Route for external access to istio gateway proxy
    - Idempotent Keycloak configuration script
key_files:
  created:
    - gateway/openshift/namespace.yaml
    - gateway/openshift/ossm-subscription.yaml
    - gateway/openshift/istio-cni.yaml
    - gateway/openshift/istio.yaml
    - gateway/openshift/cert-manager-subscription.yaml
    - gateway/openshift/keycloak-subscription.yaml
    - gateway/openshift/keycloak.yaml
    - gateway/openshift/configure-keycloak.sh
    - gateway/openshift/mcp-gateway-subscription.yaml
    - gateway/openshift/gateway.yaml
    - gateway/openshift/mcp-gateway-extension.yaml
  modified: []
decisions:
  - "GatewayClass is 'istio' (from OSSM 3.4), not 'openshift-default' as planned -- openshift-default does not exist on OCP 4.20 with OSSM 3.4"
  - "Gateway requires dual listeners (mcp + mcps) per RHCL MCP Gateway guide, not single listener as originally planned"
  - "OpenShift Route added for external access since istio GatewayClass creates LoadBalancer (may not be externally reachable without Route)"
  - "Keycloak 26+ requires email/firstName/lastName in User Profile -- configure-keycloak.sh sets these fields"
  - "cert-manager operator v1.20.1 was pre-existing on cluster -- documented subscription YAML for reproducibility"
  - "MCP Gateway Operator version is 0.7.1 (product version RHCL 1.4) -- matches channel: preview in redhat-operators catalog"
metrics:
  duration: 27 minutes
  completed: "2026-10-05T12:58:00Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 11
  files_modified: 0
---

# Phase 3 Plan 04: Gateway Infrastructure Provisioning Summary

RHCL MCP Gateway infrastructure provisioned on OCP 4.20.39 with OSSM 3.4.2, Keycloak 26.6.7, and MCP Gateway Operator 0.7.1; Gateway + MCPGatewayExtension Ready in otel25-gateway namespace; MCP initialize endpoint returning valid JSON-RPC with session management.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Verify OCP version and install prerequisite operators | e573e1e | namespace.yaml, ossm-subscription.yaml, istio-cni.yaml, istio.yaml, cert-manager-subscription.yaml, keycloak-subscription.yaml, keycloak.yaml, configure-keycloak.sh |
| 2 | Install RHCL MCP Gateway Operator and create Gateway + MCPGatewayExtension | 8edbf94 | mcp-gateway-subscription.yaml, gateway.yaml, mcp-gateway-extension.yaml |

## Infrastructure State

| Component | Version | Status | Namespace |
|-----------|---------|--------|-----------|
| OCP Cluster | 4.20.39 | Running | -- |
| OSSM Operator | 3.4.2 | CSV Succeeded | openshift-operators |
| IstioCNI | sailoperator.io/v1 | Ready | istio-cni |
| Istio Control Plane | sailoperator.io/v1 | Ready | istio-system |
| cert-manager | 1.20.1 | CSV Succeeded (pre-existing) | cert-manager-operator |
| Keycloak Operator | 26.6.7-opr.1 | CSV Succeeded | otel25-gateway |
| Keycloak Instance | mcp-keycloak | Ready | otel25-gateway |
| PostgreSQL (ephemeral) | keycloak-postgres | Running | otel25-gateway |
| MCP Gateway Operator | 0.7.1 (RHCL 1.4) | CSV Succeeded | otel25-gateway |
| Gateway (mcp-gateway) | gateway.networking.k8s.io/v1 | Programmed | otel25-gateway |
| MCPGatewayExtension | mcp.kuadrant.io/v1alpha1 | Ready | otel25-gateway |
| Gateway Proxy Pod | mcp-gateway-istio | Running 1/1 | otel25-gateway |

## Keycloak Configuration

| Item | Value |
|------|-------|
| Realm | mcp |
| Client | mcp-gateway (confidential, direct access grants) |
| Test User | mcp-agent / ***REDACTED-PASSWORD*** |
| K8s Secret | keycloak-client-secret-mcp-gateway (keys: CLIENT_SECRET, USER_PASSWORD) |
| Token Endpoint | `https://mcp-keycloak-otel25-gateway.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com/realms/mcp/protocol/openid-connect/token` |
| Token Test | PASS (access_token received, 1366 chars) |
| Configuration Script | gateway/openshift/configure-keycloak.sh (idempotent, re-runnable) |

## Gateway Endpoint

| Check | Result |
|-------|--------|
| MCP initialize | HTTP 200, JSON-RPC response with serverInfo "Kuadrant MCP Gateway" v0.0.1 |
| Session management | mcp-session-id header returned (JWT) |
| Protocol version | 2025-03-26 |
| Built-in tools | discover_tools, select_tools |
| Gateway hostname | mcp.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Keycloak hostname not configured**
- **Found during:** Task 1, Step 6
- **Issue:** Keycloak CR created without hostname, causing CrashLoopBackOff ("hostname is not configured; either configure hostname, or set hostname-strict to false")
- **Fix:** Added `spec.hostname.hostname` using the cluster apps domain
- **Files modified:** gateway/openshift/keycloak.yaml
- **Commit:** e573e1e

**2. [Rule 1 - Bug] Keycloak 26 User Profile requires email/firstName/lastName**
- **Found during:** Task 1, Step 7
- **Issue:** Token retrieval failed with "Account is not fully set up" because Keycloak 26 enforces required user profile attributes (email, firstName, lastName) by default
- **Fix:** Updated configure-keycloak.sh to set email, firstName, lastName, and emailVerified=true when creating/updating the mcp-agent user
- **Files modified:** gateway/openshift/configure-keycloak.sh
- **Commit:** e573e1e

**3. [Rule 3 - Blocking] GatewayClass 'openshift-default' does not exist**
- **Found during:** Task 2, Step 2
- **Issue:** Gateway stuck at "Waiting for controller" because `openshift-default` GatewayClass does not exist on OCP 4.20 with OSSM 3.4; the available GatewayClass is `istio`
- **Fix:** Changed `gatewayClassName: openshift-default` to `gatewayClassName: istio` in gateway.yaml
- **Files modified:** gateway/openshift/gateway.yaml
- **Commit:** 8edbf94

**4. [Rule 3 - Blocking] MCPGatewayExtension requires dual-listener Gateway and namespace in targetRef**
- **Found during:** Task 2, Step 3
- **Issue:** MCPGatewayExtension reported "gateway target /mcp-gateway not found" because: (a) Gateway had only one listener (plan spec), but RHCL requires both `mcp` and `mcps` listeners; (b) targetRef was missing the `namespace` field
- **Fix:** Added `mcps` listener (hostname: *.mcp.local), `allowedRoutes.namespaces.from: All` on both listeners, `namespace: otel25-gateway` in MCPGatewayExtension targetRef, and an OpenShift Route for external access. Applied guidance from rh-aiservices-bu/mcp-gateway-guide.
- **Files modified:** gateway/openshift/gateway.yaml, gateway/openshift/mcp-gateway-extension.yaml
- **Commit:** 8edbf94

**5. [Rule 3 - Blocking] OperatorGroup already exists in namespace**
- **Found during:** Task 2, Step 1
- **Issue:** Plan called for creating an OperatorGroup for the MCP Gateway operator, but otel25-gateway already has one (keycloak-og) from the Keycloak installation. Kubernetes namespaces can only have one OperatorGroup.
- **Fix:** Commented out OperatorGroup in mcp-gateway-subscription.yaml and documented that both operators share the existing keycloak-og OperatorGroup
- **Files modified:** gateway/openshift/mcp-gateway-subscription.yaml
- **Commit:** 8edbf94

## Decisions Made

1. **GatewayClass:** `istio` (from OSSM 3.4), not `openshift-default` -- the latter does not exist on OCP 4.20 with OSSM 3.4.2
2. **Dual listeners:** Gateway has both `mcp` (external) and `mcps` (internal *.mcp.local) listeners per RHCL MCP Gateway architecture
3. **OpenShift Route:** Added for external access to the istio gateway proxy, since the istio GatewayClass creates a LoadBalancer that may not be directly reachable
4. **MCP Gateway version:** Operator v0.7.1 corresponds to RHCL 1.4 product version (the version numbering differs between the OLM catalog and the product name)
5. **Shared OperatorGroup:** The keycloak-og OperatorGroup in otel25-gateway is shared by both the Keycloak and MCP Gateway operators

## Known Stubs

None -- all infrastructure is live and verified.

## Self-Check: PASSED

- [x] gateway/openshift/namespace.yaml exists
- [x] gateway/openshift/ossm-subscription.yaml exists
- [x] gateway/openshift/istio-cni.yaml exists
- [x] gateway/openshift/istio.yaml exists
- [x] gateway/openshift/cert-manager-subscription.yaml exists
- [x] gateway/openshift/keycloak-subscription.yaml exists
- [x] gateway/openshift/keycloak.yaml exists
- [x] gateway/openshift/configure-keycloak.sh exists
- [x] gateway/openshift/mcp-gateway-subscription.yaml exists
- [x] gateway/openshift/gateway.yaml exists
- [x] gateway/openshift/mcp-gateway-extension.yaml exists
- [x] Commit e573e1e exists in git log
- [x] Commit 8edbf94 exists in git log
