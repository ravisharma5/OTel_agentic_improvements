---
phase: 3
slug: mcp-domain-servers-and-gateway
status: active
nyquist_compliant: true
wave_0_complete: true
created: 2026-10-04
updated: 2026-10-04
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
| 03-02 T1 verify + 03-05 T2 | 03-02, 03-05 | 2, 3 | MCP-01 | — | 6 TMF642 tools listed by server | smoke | `scripts/verify-domain-tools.sh tmf642` | 03-01 W0 | ⬜ pending |
| 03-05 T2 | 03-05 | 3 | MCP-01 | — | Each TMF642 tool returns valid response from Prism | integration | `scripts/verify-domain-tools.sh tmf642` | 03-01 W0 | ⬜ pending |
| 03-02 T2 verify + 03-05 T2 | 03-02, 03-05 | 2, 3 | MCP-02 | — | 5 TMF628 tools listed by server | smoke | `scripts/verify-domain-tools.sh tmf628` | 03-01 W0 | ⬜ pending |
| 03-05 T2 | 03-05 | 3 | MCP-02 | — | Each TMF628 tool returns valid response from Prism | integration | `scripts/verify-domain-tools.sh tmf628` | 03-01 W0 | ⬜ pending |
| 03-02 T2 verify + 03-05 T2 | 03-02, 03-05 | 2, 3 | MCP-03 | — | 4 TMF621 tools listed by server | smoke | `scripts/verify-domain-tools.sh tmf621` | 03-01 W0 | ⬜ pending |
| 03-05 T2 | 03-05 | 3 | MCP-03 | — | Each TMF621 tool returns valid response from Prism | integration | `scripts/verify-domain-tools.sh tmf621` | 03-01 W0 | ⬜ pending |
| 03-03 T1 verify + 03-05 T2 | 03-03, 03-05 | 2, 3 | MCP-04 | — | 3 NWDAF tools listed by server | smoke | `scripts/verify-domain-tools.sh nwdaf` | 03-01 W0 | ⬜ pending |
| 03-05 T2 | 03-05 | 3 | MCP-04 | — | Each NWDAF tool returns valid response from Prism | integration | `scripts/verify-domain-tools.sh nwdaf` | 03-01 W0 | ⬜ pending |
| 03-03 T2 verify + 03-05 T2 | 03-03, 03-05 | 2, 3 | MCP-05 | — | 2 CAMARA tools listed by server | smoke | `scripts/verify-domain-tools.sh camara` | 03-01 W0 | ⬜ pending |
| 03-05 T2 | 03-05 | 3 | MCP-05 | — | Each CAMARA tool returns valid response from Prism | integration | `scripts/verify-domain-tools.sh camara` | 03-01 W0 | ⬜ pending |
| 03-04 T2 | 03-04 | 1 | MCP-08 | T-03-01 | Gateway initialize returns valid JSON-RPC | smoke | `scripts/verify-gateway.sh initialize` | 03-01 W0 | ⬜ pending |
| 03-06 T2 | 03-06 | 4 | MCP-08 | T-03-01 | All 78 tools visible via gateway tools/list | integration | `scripts/verify-gateway.sh tools-list` | 03-01 W0 | ⬜ pending |
| 03-06 T2 | 03-06 | 4 | MCP-08 | — | TMF virtual server filters to 15 tools | integration | `scripts/verify-gateway.sh virtual-tmf` | 03-01 W0 | ⬜ pending |
| 03-06 T2 | 03-06 | 4 | MCP-08 | — | Tool call through gateway returns backend response | e2e | `scripts/verify-gateway.sh tool-call` | 03-01 W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

**Coverage notes:**
- Smoke tests (tool count validation) have dual coverage: code-level verification in build plans (03-02/03-03 task verify steps) and MCP-protocol-level verification in deployment plan (03-05 Task 2 via verify-domain-tools.sh).
- Integration tests (Prism backend responses) are exercised only after deployment (03-05 Task 2) since they require running backends.
- Gateway tests require both gateway infrastructure (03-04, Wave 1) and backend registration (03-06, Wave 4).

---

## Wave 0 Requirements

- [x] `scripts/verify-domain-tools.sh` — parameterized per-domain verification (tmf642/tmf628/tmf621/nwdaf/camara) — created in 03-01 Task 2
- [x] `scripts/verify-gateway.sh` — gateway endpoint verification (initialize, tools-list, virtual-tmf, tool-call) — created in 03-01 Task 2
- [ ] Per-server `tests/` directories with unit tests for hand-curated tool customizations (e.g. TMF642's PATCH-based acknowledge/clear/comment split) — created within 03-02/03-03 as needed

---

## Manual-Only Verifications

*All phase behaviors have automated verification — no manual-only verifications identified.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references (03-01 creates both verification scripts)
- [x] No watch-mode flags
- [x] Feedback latency < 120s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** 2026-10-04
