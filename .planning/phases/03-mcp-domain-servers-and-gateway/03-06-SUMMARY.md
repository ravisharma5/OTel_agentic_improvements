---
phase: 03-mcp-domain-servers-and-gateway
plan: 06
subsystem: gateway-registration
tags: [rhcl, mcp-gateway, mcpserverregistration, mcpvirtualserver, authpolicy, keycloak, jwt, gateway-api]
dependency_graph:
  requires:
    - plan: 03-04
      provides: Gateway + MCPGatewayExtension + Keycloak in otel25-gateway namespace
    - plan: 03-05
      provides: 5 domain MCP server deployments + MCP-Telecom in otel25-mcp namespace
  provides:
    - 6 MCPServerRegistrations (tmf642, tmf628, tmf621, nwdaf, camara, telecom) all Ready
    - 4 MCPVirtualServers (tmf-tools 15, nwdaf-tools 3, camara-tools 2, infra-tools 58)
    - AuthPolicy JWT authentication on MCP gateway
    - ReferenceGrant for cross-namespace HTTPRoute access
    - Gateway tools/list returns 80 tools (78 backend + 2 gateway meta-tools)
    - End-to-end tool call through gateway returns Prism backend response
  affects:
    - Phase 4 SDG pipeline connects to this gateway endpoint as tool source
tech_stack:
  added:
    - Authorino Operator 1.4.3 (moved to openshift-operators for AllNamespaces mode)
    - RHCL Operator 1.4.3 (moved to openshift-operators for AllNamespaces mode)
    - Limitador Operator 1.4.2 (RHCL dependency)
    - DNS Operator 1.4.2 (RHCL dependency)
    - Kuadrant CR (enables RHCL policy reconciliation)
  patterns:
    - MCPServerRegistration with HTTPRoute targetRef and cross-namespace ReferenceGrant
    - MCPVirtualServer tool filtering via X-Mcp-Virtualserver header
    - AuthPolicy defaults block with JWT issuerUrl from Keycloak
    - *.mcp.local hostname pattern for internal backend routing on mcps listener
    - mcp-system namespace for MCPVirtualServer config secret (RHCL Tech Preview behavior)
key_files:
  created:
    - gateway/openshift/reference-grant.yaml
    - gateway/openshift/httproute-tmf642.yaml
    - gateway/openshift/httproute-tmf628.yaml
    - gateway/openshift/httproute-tmf621.yaml
    - gateway/openshift/httproute-nwdaf.yaml
    - gateway/openshift/httproute-camara.yaml
    - gateway/openshift/httproute-telecom.yaml
    - gateway/openshift/mcpsr-tmf642.yaml
    - gateway/openshift/mcpsr-tmf628.yaml
    - gateway/openshift/mcpsr-tmf621.yaml
    - gateway/openshift/mcpsr-nwdaf.yaml
    - gateway/openshift/mcpsr-camara.yaml
    - gateway/openshift/mcpsr-telecom.yaml
    - gateway/openshift/mcpvs-tmf.yaml
    - gateway/openshift/mcpvs-nwdaf.yaml
    - gateway/openshift/mcpvs-camara.yaml
    - gateway/openshift/mcpvs-infra.yaml
    - gateway/openshift/auth-policy.yaml
    - gateway/openshift/authorino-subscription.yaml
    - gateway/openshift/kuadrant.yaml
    - gateway/openshift/rhcl-deps-subscription.yaml
    - scripts/run-gateway-verify.sh
    - scripts/drift-check.sh
    - scripts/check-config.py
  modified:
    - scripts/verify-gateway.sh
decisions:
  - "MCPServerRegistration prefix concatenates without underscore separator (e.g. tmf642listAlarm, not tmf642_list_alarms) -- this is the RHCL gateway's actual behavior, not what the docs implied"
  - "HTTPRoutes require hostnames matching the mcps listener wildcard (*.mcp.local) -- RHCL rejects backend HTTPRoutes without at least one hostname"
  - "Authorino, RHCL, Limitador, DNS operators moved from otel25-gateway to openshift-operators namespace because they do not support OwnNamespace InstallModeType"
  - "mcp-system namespace created for MCPVirtualServer config secret -- RHCL controller writes virtual server config there by default, not to the gateway namespace"
  - "Virtual server config merged into otel25-gateway/mcp-gateway-config secret -- broker reads config from its own namespace, not from mcp-system"
  - "AuthPolicy uses spec.defaults block (when + rules together) -- mixing defaults.when with top-level rules is rejected by the CRD validator"
  - "2 gateway meta-tools (discover_tools, select_tools) appear in tools/list alongside the 78 backend tools -- these are RHCL gateway-provided tools, not from any backend"
metrics:
  duration: 20 minutes
  completed: "2026-10-05T14:20:00Z"
  tasks_completed: 2
  tasks_total: 2
  files_created: 24
  files_modified: 1
---

# Phase 3 Plan 06: Gateway Registration and End-to-End Verification Summary

6 MCPServerRegistrations with cross-namespace HTTPRoutes, 4 per-domain MCPVirtualServers with drift-verified tool lists, and JWT AuthPolicy via Keycloak -- all verified end-to-end with 80 tools visible, TMF virtual server filtering to exactly 15, and tool invocation returning Prism backend data through the RHCL MCP Gateway.

## Tasks Completed

| Task | Name | Commit | Key Files |
|------|------|--------|-----------|
| 1 | Create ReferenceGrant, HTTPRoutes, and MCPServerRegistrations for all 6 backends | 7a70802 | reference-grant.yaml, httproute-*.yaml (6), mcpsr-*.yaml (6) |
| 2 | Create MCPVirtualServers, AuthPolicy, and verify end-to-end gateway operation | c2d0f48 | mcpvs-*.yaml (4), auth-policy.yaml, authorino-subscription.yaml, kuadrant.yaml, rhcl-deps-subscription.yaml, verify-gateway.sh, drift-check.sh |

## Gateway State

### MCPServerRegistrations (6 Ready)

| Name | Prefix | Discovered Tools | Backend Service |
|------|--------|-----------------|-----------------|
| tmf642 | tmf642 | 6 | mcp-tmf642.otel25-mcp:8000 |
| tmf628 | tmf628 | 5 | mcp-tmf628.otel25-mcp:8000 |
| tmf621 | tmf621 | 4 | mcp-tmf621.otel25-mcp:8000 |
| nwdaf | nwdaf | 3 | mcp-nwdaf.otel25-mcp:8000 |
| camara | camara | 2 | mcp-camara.otel25-mcp:8000 |
| telecom | telecom | 58 | mcp-telecom.otel25-mcp:8000 |

### MCPVirtualServers (4 configured, drift-verified)

| Name | Tool Count | Domain |
|------|-----------|--------|
| tmf-tools | 15 | TMF642 (6) + TMF628 (5) + TMF621 (4) |
| nwdaf-tools | 3 | NWDAF analytics + event subscriptions |
| camara-tools | 2 | CAMARA device location verify + retrieve |
| infra-tools | 58 | MCP-Telecom infrastructure/device tools |

### AuthPolicy

| Field | Value |
|-------|-------|
| Name | mcp-auth |
| Target | Gateway/mcp-gateway, sectionName: mcp |
| Status | Accepted=True |
| Issuer | https://mcp-keycloak-otel25-gateway.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com/realms/mcp |
| Excluded paths | /.well-known/* |
| Unauth response | 401 with JSON error body |

## Verification Results

| Test | Result | Details |
|------|--------|---------|
| Unauthenticated POST /mcp | PASS | Returns HTTP 401 |
| Authenticated initialize | PASS | JSON-RPC 2.0, serverInfo: Kuadrant MCP Gateway v0.0.1 |
| Authenticated tools/list | PASS | 80 tools (78 backend + 2 gateway meta) |
| Virtual TMF filter | PASS | Exactly 15 TMF tools |
| Tool call (tmf642listAlarm) | PASS | Returns Prism alarm data through gateway |
| Drift-check tmf-tools | PASS | 15/15 exact match |
| Drift-check nwdaf-tools | PASS | 3/3 exact match |
| Drift-check camara-tools | PASS | 2/2 exact match |
| Drift-check infra-tools | PASS | 58/58 exact match |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] HTTPRoutes missing required hostnames**
- **Found during:** Task 1, Step 2
- **Issue:** RHCL MCP Gateway requires HTTPRoutes to have at least one hostname matching the mcps listener wildcard (*.mcp.local). The 03-RESEARCH.md example omitted hostnames.
- **Fix:** Added `hostnames: [<prefix>.mcp.local]` to all 6 HTTPRoutes
- **Files modified:** httproute-tmf642.yaml through httproute-telecom.yaml
- **Commit:** 7a70802

**2. [Rule 3 - Blocking] Authorino/RHCL/Limitador/DNS operators failed with OwnNamespace mode**
- **Found during:** Task 2, Step 2
- **Issue:** The OperatorGroup in otel25-gateway uses OwnNamespace InstallModeType which Authorino, RHCL, Limitador, and DNS operators do not support. Without Authorino, AuthPolicy has no controller to reconcile it.
- **Fix:** Deleted failed subscriptions from otel25-gateway, created new subscriptions in openshift-operators (AllNamespaces mode). All 4 CSVs now Succeeded.
- **Files created:** authorino-subscription.yaml, rhcl-deps-subscription.yaml
- **Commit:** c2d0f48

**3. [Rule 3 - Blocking] Kuadrant CR required for RHCL policy reconciliation**
- **Found during:** Task 2, Step 2
- **Issue:** AuthPolicy status remained empty because no Kuadrant CR existed to enable RHCL policy reconciliation.
- **Fix:** Created kuadrant.yaml with minimal Kuadrant CR in otel25-gateway namespace. Kuadrant CR status: Ready=True.
- **Files created:** kuadrant.yaml
- **Commit:** c2d0f48

**4. [Rule 3 - Blocking] AuthPolicy CRD rejects mixed defaults/rules structure**
- **Found during:** Task 2, Step 2
- **Issue:** AuthPolicy with `spec.defaults.when` and `spec.rules` (top-level) is rejected as "Implicit and explicit defaults are mutually exclusive".
- **Fix:** Moved `rules` under `defaults` to create `spec.defaults.when` + `spec.defaults.rules` structure.
- **Files modified:** auth-policy.yaml
- **Commit:** c2d0f48

**5. [Rule 3 - Blocking] MCPVirtualServer controller writes to mcp-system namespace (not found)**
- **Found during:** Task 2, Step 1
- **Issue:** MCPVirtualServer controller reconciliation failed with "namespaces mcp-system not found". The RHCL controller defaults to writing virtual server config secrets in mcp-system.
- **Fix:** Created mcp-system namespace. After creation, controller successfully wrote virtual server configs. Merged virtualServers into otel25-gateway/mcp-gateway-config secret so the broker (which reads from its own namespace) picks them up. Broker restart required.
- **Commit:** c2d0f48

**6. [Rule 1 - Bug] verify-gateway.sh tool name mismatch**
- **Found during:** Task 2, Step 4
- **Issue:** TOOLCALL_TOOL_NAME was `tmf642_list_alarms` but actual discovered name is `tmf642listAlarm` (prefix concatenated without underscore, camelCase operationId).
- **Fix:** Updated TOOLCALL_TOOL_NAME to `tmf642listAlarm`.
- **Files modified:** scripts/verify-gateway.sh
- **Commit:** c2d0f48

## ROADMAP Success Criteria Verification

| Criterion | Status | Evidence |
|-----------|--------|----------|
| #2: Gateway composes all domain servers + MCP-Telecom with namespacing, single endpoint | PASS | 80 tools via single /mcp endpoint, 4 MCPVirtualServers for per-domain filtering |
| #3: Tool call through gateway returns correct backend response | PASS | tmf642listAlarm returns Prism alarm data (JSON array with alarm objects) |
| D-05: MCP-Telecom registered | PASS | telecom MCPServerRegistration Ready, 58 tools discovered |
| D-06: 6 MCPServerRegistrations | PASS | All 6 Ready with correct tool counts |
| D-07: Per-domain Virtual MCP Servers | PASS | tmf-tools (15), nwdaf-tools (3), camara-tools (2), infra-tools (58) |
| D-08: AuthPolicy with JWT configured | PASS | mcp-auth Accepted, unauthenticated returns 401 |

## Known Issues

- **MCPServerRegistration prefix concatenation**: RHCL concatenates the prefix directly without an underscore separator. Tool names are e.g. `tmf642listAlarm` not `tmf642_list_alarms`. The 03-RESEARCH.md documentation example showed underscore separation but the actual behavior does not include one.
- **Gateway meta-tools**: 2 additional tools (`discover_tools`, `select_tools`) appear in tools/list that are not from any backend. These are RHCL gateway-provided tools. Total count is 80, not 78.
- **NWDAF tool id missing**: Broker logs show "unable to check conflict, tool id is missing" for NWDAF and CAMARA tools. Does not affect tool listing or invocation but may indicate a metadata gap in the NWDAF/CAMARA MCP servers.
- **Virtual server config dual-write**: MCPVirtualServer controller writes to mcp-system/mcp-gateway-config, but the broker reads from otel25-gateway/mcp-gateway-config. The virtualServers section was manually merged. If MCPServerRegistrations are re-reconciled (adding/removing a backend), the controller may overwrite the otel25-gateway config without virtualServers. Solution: ensure mcp-system config is the authoritative source and always merge after MCPServerRegistration changes.

## Self-Check: PASSED

All 24 created files verified present. Both commit hashes (7a70802, c2d0f48) verified in git log.
