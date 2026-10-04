# Phase 3: MCP Domain Servers and Gateway - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-04
**Phase:** 3-MCP Domain Servers and Gateway
**Areas discussed:** Gateway architecture, Tool namespacing scheme, Per-tool verification approach, Auth/policy scope, Infrastructure prerequisites, Deployment namespace

---

## Gateway Architecture — Product Identity

| Option | Description | Selected |
|--------|-------------|----------|
| Research it | No specific reference in mind — have researcher investigate current Kuadrant MCP capabilities | ✓ (initial answer) |
| I have a reference | User has a specific pattern in mind | |
| Kuadrant does everything | Kuadrant itself routes/composes with no FastMCP layer | |

**User's choice:** Initially "Research it," but the user then clarified directly: "We want to use MCP Gateway from Red Hat to front these MCP tools, for tool filtering, virtual MCP servers, and other features." When asked to identify the exact product (offered IBM MCP Context Forge as a guess), the user supplied the authoritative source: `https://docs.kuadrant.io/1.5.x/mcp-gateway/docs/guides/overview/`, then corrected further to the actual target: Red Hat Connectivity Link (RHCL) 1.4, with install docs at `https://docs.redhat.com/en/documentation/red_hat_connectivity_link/1.4/html/install_the_mcp_gateway/index`.

**Notes:** Claude's first framing (FastMCP `mount()` vs. Kuadrant as alternatives) was incorrect — it missed that Kuadrant/RHCL ships an actual MCP-protocol-aware gateway product (Envoy + Gateway API based) with Virtual MCP Servers, tool filtering, and MCPServerRegistration. Claude fetched both the upstream Kuadrant docs (found: "early preview feature... not production-ready") and the RHCL 1.4 docs (found: Technology Preview, 1.4.0 deprecated, 1.4.1+ recommended, MCPGatewayExtension CR, OLM install flow) to ground the decision. See CONTEXT.md D-01 through D-04.

---

## Gateway Architecture — Version, Fallback Risk, TP Status

| Option | Description | Selected |
|--------|-------------|----------|
| Timebox, then fallback | Mirror Phase 1 NextGCore precedent | (superseded once RHCL confirmed) |
| Commit to it regardless | No fallback plan | |
| Research maturity first | Dig into GitHub issues/release notes before deciding | |

**User's choice (after RHCL confirmed):** 1.4.1+ version pin (not 1.4.0) — "Yes, 1.4.1+." Technology Preview status accepted as-is — "Yes, acceptable." No fallback architecture pre-built.

**Notes:** The upstream-Kuadrant-preview risk question was asked before the user clarified RHCL was the actual target; once RHCL's own docs were fetched (confirming Technology Preview + 1.4.0 deprecation), the user re-answered directly against that information.

---

## MCP-Telecom Inclusion

| Option | Description | Selected |
|--------|-------------|----------|
| Proxy it in / Yes, include it | Register MCP-Telecom as a gateway backend alongside the 5 new servers | ✓ |
| Leave it separate | MCP-Telecom stays reachable only at its own Phase 2 endpoint | |

**User's choice:** Include it — all 78 tools (20 new + 58 MCP-Telecom) reachable through the one gateway.

---

## Gateway Namespace

| Option | Description | Selected |
|--------|-------------|----------|
| otel25-mcp | Same namespace as domain servers/MCP-Telecom | |
| New namespace | Dedicated namespace for gateway resources | ✓ |

**User's choice:** New namespace for the gateway itself (separate from where domain servers/MCP-Telecom live).

---

## Tool Namespacing Scheme — Virtual MCP Server Granularity

| Option | Description | Selected |
|--------|-------------|----------|
| One unified virtual server | All 78 tools as a single curated list | |
| Per-domain virtual servers | Separate virtual servers for TMF, NWDAF, CAMARA, infra | ✓ |
| Undecided — research recommends | Defer to researcher based on Phase 4 SDG needs | |

**User's choice:** Per-domain virtual servers.

---

## Auth/Policy Scope

| Option | Description | Selected |
|--------|-------------|----------|
| Configure it now | Set up RHCL's MCP-gateway AuthPolicy in Phase 3 | ✓ |
| Defer to later phase | Leave endpoint unauthenticated, cluster-internal only | |

**User's choice:** Configure it now — closes Phase 2's flagged ClusterIP-only exposure gap (T-02-01).

---

## Per-Tool Verification Approach

| Option | Description | Selected |
|--------|-------------|----------|
| Prism mocks for all 20 | Fast, deterministic; live NextGCore is a stretch goal | ✓ |
| Prism + live NextGCore required | Higher bar for the 3 NWDAF tools | |

**User's choice:** Prism mocks for all 20; live NextGCore verification not required.

---

## Infrastructure Prerequisites

| Option | Description | Selected |
|--------|-------------|----------|
| Not set up — provision in Phase 3 | Treat RHCL Operator + Gateway API/Service Mesh install as in-scope setup work | ✓ |
| Already installed | Infra pre-exists from outside this project | |
| Unknown — verify first | Research/planning checks before committing | |

**User's choice:** Not set up — provisioning is in-scope for Phase 3, mirroring Phase 1's cluster/CLI provisioning precedent.

---

## Domain Server Deployment Namespace

| Option | Description | Selected |
|--------|-------------|----------|
| otel25-mcp | Same namespace as MCP-Telecom | ✓ |
| New namespace per domain | Separate namespace per API family | |

**User's choice:** otel25-mcp — continues Phase 2's namespace-per-layer pattern. Only the gateway itself gets the new namespace.

---

## Claude's Discretion

- Exact `MCPServerRegistration` and `MCPGatewayExtension` resource naming/field values.
- New gateway namespace name.
- Whether in-cluster backend registration needs the full "external MCP server" flow (ServiceEntry/TLS/Secret) or a lighter in-cluster path.
- Exact tool-naming scheme within each per-domain Virtual MCP Server.

## Deferred Ideas

None — discussion stayed within phase scope.
