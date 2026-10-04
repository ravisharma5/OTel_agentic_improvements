---
phase: 3
slug: mcp-domain-servers-and-gateway
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-10-04
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >= 8.0 (project standard) |
| **Config file** | Per-server `pytest.ini` or shared in `mcp/` |
| **Quick run command** | `cd mcp/<server> && uv run pytest tests/ -x --timeout=30` |
| **Full suite command** | `cd mcp/<server> && uv run pytest tests/ -v` + `scripts/verify-domain-tools.sh` + `scripts/verify-gateway.sh` |
| **Estimated runtime** | ~60-120 seconds (5 domain servers + gateway verification) |

---

## Sampling Rate

- **After every task commit:** Run the quick smoke test for the specific server being built (`cd mcp/<server> && uv run pytest tests/ -x --timeout=30`)
- **After every plan wave:** Run the full suite for all completed servers + `scripts/verify-gateway.sh`
- **Before `/gsd:verify-work`:** Full suite must be green — all 20 tools individually callable, gateway composes all 78, virtual servers filter correctly
- **Max feedback latency:** 120 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | MCP-01 | — | 6 TMF642 tools listed by server | smoke | `curl POST localhost:8000/mcp tools/list \| jq '.result.tools \| length' == 6` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | MCP-01 | — | Each TMF642 tool returns valid response from Prism | integration | `scripts/verify-domain-tools.sh tmf642` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | MCP-02 | — | 5 TMF628 tools listed by server | smoke | same pattern, == 5 | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | MCP-02 | — | Each TMF628 tool returns valid response from Prism | integration | `scripts/verify-domain-tools.sh tmf628` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | MCP-03 | — | 4 TMF621 tools listed by server | smoke | same pattern, == 4 | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | MCP-03 | — | Each TMF621 tool returns valid response from Prism | integration | `scripts/verify-domain-tools.sh tmf621` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | MCP-04 | — | 3 NWDAF tools listed by server | smoke | same pattern, == 3 | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | MCP-04 | — | Each NWDAF tool returns valid response from Prism | integration | `scripts/verify-domain-tools.sh nwdaf` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | MCP-05 | — | 2 CAMARA tools listed by server | smoke | same pattern, == 2 | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | MCP-05 | — | Each CAMARA tool returns valid response from Prism | integration | `scripts/verify-domain-tools.sh camara` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | MCP-08 | T-02-01 | Gateway initialize returns valid JSON-RPC | smoke | `scripts/verify-gateway.sh initialize` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | MCP-08 | T-02-01 | All 78 tools visible via gateway tools/list | integration | `scripts/verify-gateway.sh tools-list` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | MCP-08 | — | TMF virtual server filters to 15 tools | integration | `scripts/verify-gateway.sh virtual-tmf` | ❌ W0 | ⬜ pending |
| TBD | TBD | TBD | MCP-08 | — | Tool call through gateway returns backend response | e2e | `scripts/verify-gateway.sh tool-call` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
*Task ID / Plan / Wave columns are filled in by the planner once PLAN.md files assign these tests to concrete tasks.*

---

## Wave 0 Requirements

- [ ] `scripts/verify-domain-tools.sh` — parameterized per-domain verification (tmf642/tmf628/tmf621/nwdaf/camara)
- [ ] `scripts/verify-gateway.sh` — gateway endpoint verification (initialize, tools-list, virtual-tmf, tool-call)
- [ ] Per-server `tests/` directories with unit tests for hand-curated tool customizations (e.g. TMF642's PATCH-based acknowledge/clear/comment split)

---

## Manual-Only Verifications

*All phase behaviors have automated verification — no manual-only verifications identified.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 120s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
