# Phase 2: MCP Tooling Foundation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-10-02
**Phase:** 2-MCP Tooling Foundation
**Areas discussed:** MCP-Telecom transport bridging, MCP-Telecom backend data source, Conversion tooling shape, Deployment layout, MIT license compliance for vendored fork, Safe-CLI-exec tool guardrails, OpenShift health probes

---

## MCP-Telecom Transport Bridging

| Option | Description | Selected |
|--------|-------------|----------|
| stdio-to-HTTP proxy sidecar | Run MCP-Telecom unmodified, front it with a bridge (mcp-proxy/supergateway) | |
| Fork/patch for native HTTP | Add FastMCP's HTTP/SSE transport directly to MCP-Telecom's source | ✓ |
| Stay stdio, defer bridging | Validate via oc exec/port-forward for Phase 2, punt bridging to Phase 3 | |

**User's choice:** Fork/patch for native HTTP transport.
**Notes:** Follow-up revealed MCP-Telecom is already FastMCP-based, so the patch is expected to be small (entrypoint/config change, not a deep fork) — user confirmed treating it as a proper vendored+patched copy regardless.

| Option | Description | Selected |
|--------|-------------|----------|
| Vendor into this repo | Copy source into repo, patch directly, no upstream tracking | ✓ |
| Separate GitHub fork | Fork on GitHub, patch there, pull as dependency/submodule | |
| Upstream PR, wait for merge | Contribute patch upstream, depend on merge | |

**User's choice:** Vendor into this repo — matches Phase 1's vendoring precedent (01-CONTEXT.md D-06).

| Option | Description | Selected |
|--------|-------------|----------|
| Support both (flag/env toggle) | Keep stdio for local dev, HTTP opt-in for OpenShift | |
| HTTP-only | Strip stdio, run HTTP/SSE exclusively | ✓ |

**User's choice:** HTTP-only.

| Option | Description | Selected |
|--------|-------------|----------|
| Streamable HTTP | Current MCP 2026-07-28 protocol transport | ✓ |
| Legacy SSE | Older transport, being phased out | |

**User's choice:** Streamable HTTP.

| Option | Description | Selected |
|--------|-------------|----------|
| Still vendor + patch as planned | Confirms earlier decision stands | ✓ |
| Reconsider — maybe no fork needed | Thin wrapper importing MCP-Telecom as dependency | |

**User's choice:** Still vendor + patch as planned.

| Option | Description | Selected |
|--------|-------------|----------|
| mcp-telecom, dedicated port | Service name + port matching Phase 1's per-service pattern | |
| Leave naming to executor | Don't lock specifics now | ✓ |

**User's choice:** Leave naming to executor (Claude's discretion).

---

## MCP-Telecom Backend Data Source

| Option | Description | Selected |
|--------|-------------|----------|
| Point at nothing / leave unconfigured | Tools deployed, callable, error on invocation | ✓ |
| Stand up a lightweight device simulator | containerlab or NETCONF/SSH simulator for realistic responses | |
| Defer the whole question to Phase 4 | Treat backend wiring as entirely out of scope | |

**User's choice:** Point at nothing / leave unconfigured.

| Option | Description | Selected |
|--------|-------------|----------|
| MCP listTools + one sample call per tool | Proves full protocol round-trip | ✓ |
| listTools only, no invocation | Lighter verification | |

**User's choice:** MCP listTools + one sample call per tool.

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, flag it in STATE.md | Known Blocker/Concern for Phase 4 SDG planner | ✓ |
| No, don't flag separately | Leave implicit in CONTEXT.md only | |

**User's choice:** Yes, flag it in STATE.md.

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, scaffold the config shape now | devices.yaml with placeholders | ✓ |
| No, leave it fully absent | Phase 4 builds config from scratch | |

**User's choice:** Yes, scaffold the config shape now.

| Option | Description | Selected |
|--------|-------------|----------|
| OpenShift Secret reference | Config references a Secret, left empty in Phase 2 | ✓ |
| Plain placeholder in config file | Placeholder strings directly in ConfigMap | |

**User's choice:** OpenShift Secret reference.

---

## Conversion Tooling Shape

| Option | Description | Selected |
|--------|-------------|----------|
| Generic CLI/script Phase 3 invokes | Standalone script scaffolds a curated FastMCP server per spec | ✓ |
| Shared Python library/module | Function/class Phase 3 imports inline | |
| Documented pattern only | No new code, just a written convention | |

**User's choice:** Generic CLI/script Phase 3 invokes.

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, smoke-test against CAMARA Device Location | Confirms CLI produces a working server | ✓ |
| No, defer first real use to Phase 3 | Build/unit-test in isolation only | |

**User's choice:** Yes, smoke-test against CAMARA Device Location.

| Option | Description | Selected |
|--------|-------------|----------|
| YAML/JSON allowlist config | Declarative operationId/tag list | ✓ |
| CLI flags | Operation IDs as command-line arguments | |

**User's choice:** YAML/JSON allowlist config.

| Option | Description | Selected |
|--------|-------------|----------|
| One-time codegen, then hand-curate | CLI writes server.py once, Phase 3 edits committed file | ✓ |
| Dynamic runtime loader | Reads spec + config live at startup, no generated file | |

**User's choice:** One-time codegen, then hand-curate.

---

## Deployment Layout

| Option | Description | Selected |
|--------|-------------|----------|
| New namespace (otel25-mcp) | Separate MCP-layer workloads from backend mocks | ✓ |
| Reuse otel25-backends | Keep everything in one namespace | |

**User's choice:** New namespace (otel25-mcp).

| Option | Description | Selected |
|--------|-------------|----------|
| Plain YAML manifests | Continue Phase 1's pattern | ✓ |
| Introduce Helm | Start templated deployments now | |

**User's choice:** Plain YAML manifests.

| Option | Description | Selected |
|--------|-------------|----------|
| New top-level mcp/ directory | mcp/tooling/ and mcp/mcp-telecom/, parallel to backends/ | ✓ |
| Leave layout to executor | Don't lock directory names now | |

**User's choice:** New top-level mcp/ directory.

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, bake it into the scaffold | Every generated server includes ConfigMap file-watching | ✓ |
| No, Phase 3's job | Leave backend-URL wiring entirely to Phase 3 | |

**User's choice:** Yes, bake it into the scaffold.

| Option | Description | Selected |
|--------|-------------|----------|
| Local only, not deployed | CAMARA smoke-test server confirmed locally only | ✓ |
| Deploy it to OpenShift too | Push smoke-test server to otel25-mcp as well | |

**User's choice:** Local only, not deployed.

---

## MIT License Compliance for Vendored Fork

| Option | Description | Selected |
|--------|-------------|----------|
| Keep MIT, isolate in its own dir, attribute clearly | Vendored subtree keeps MIT + NOTICE, Apache 2.0 applies elsewhere | ✓ |
| Flag as an open question for legal/WG review | Defer decision to legal/WG reviewer | |

**User's choice:** Keep MIT, isolate in its own dir, attribute clearly.

---

## Safe-CLI-exec Tool Guardrails

| Option | Description | Selected |
|--------|-------------|----------|
| Yes, scaffold an allowlist now | Config-driven command allowlist placeholder added now | ✓ |
| No, defer entirely to Phase 4 | Leave MCP-Telecom's built-in mechanism as-is | |

**User's choice:** Yes, scaffold an allowlist now.

---

## OpenShift Health Probes

| Option | Description | Selected |
|--------|-------------|----------|
| Process-up / MCP endpoint responds | Liveness checks port alive, readiness checks tools/list | ✓ |
| Leave probe design to executor | Standard K8s probe design, no user input needed | |

**User's choice:** Process-up / MCP endpoint responds.

---

## Claude's Discretion

- Exact Service/port naming for the deployed MCP-Telecom.
- Exact shape/filenames of the device-inventory scaffold and command-allowlist scaffold, as long as credentials reference OpenShift Secrets.
- Exact YAML allowlist-config schema for the conversion CLI, as long as it supports operationId/tag selection.

## Deferred Ideas

None — discussion stayed within phase scope. Wiring MCP-Telecom to real network devices, the 20 curated domain tools, and the Kuadrant MCP Gateway composition were all explicitly recognized as Phase 3/4 work, not pulled forward.
