---
phase: 4
slug: sdg-pipeline-and-dataset-production
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-10-05
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest (existing in `mcp/mcp-telecom`) + manual notebook validation for the SDG pipeline itself |
| **Config file** | `mcp/mcp-telecom/pyproject.toml` (existing) |
| **Quick run command** | `cd mcp/mcp-telecom && uv run pytest tests/ -x --timeout 30` |
| **Full suite command** | `cd mcp/mcp-telecom && uv run pytest tests/ -v` |
| **Estimated runtime** | ~30-60 seconds (unit suite); manual notebook/dry-run steps are out-of-band |

---

## Sampling Rate

- **After every task commit:** Run `cd mcp/mcp-telecom && uv run pytest tests/ -x --timeout 30` for any MCP-Telecom changes (CR-01/02/03 fixes, device inventory)
- **After every plan wave:** Full MCP-Telecom suite (`uv run pytest tests/ -v`) + relevant manual notebook/dry-run validation for that wave's SDG pipeline work
- **Before `/gsd:verify-work`:** Full suite must be green, plus Farbod's team confirms the 10-example OSFT dry-run (D-19)
- **Max feedback latency:** 60 seconds for automated tests; manual steps (dry-run, Containerlab topology verification) are expected to take longer and are tracked separately, not part of the fast feedback loop

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-0X-0X | TBD | TBD | SDG-01 | — | sdg_hub flow connects to MCP Gateway and generates traces | manual | Manual: run `01-dry-run.ipynb` | ❌ W0 | ⬜ pending |
| 04-0X-0X | TBD | TBD | SDG-02 | — | Curriculum ordering produces examples in correct progression | manual | Manual: inspect output distribution | ❌ W0 | ⬜ pending |
| 04-0X-0X | TBD | TBD | SDG-03 | — | Both single-turn and multi-turn JSONL formats valid | unit | `pytest sdg/scripts/test_serialize_osft.py -x` | ❌ W0 | ⬜ pending |
| 04-0X-0X | TBD | TBD | SDG-04 | — | Quality filtering reduces raw count to 5K-10K target range | manual | Manual: count rows post-filter | ❌ W0 | ⬜ pending |
| 04-0X-0X | TBD | TBD | SDG-05 | — | JSONL validates against OSFT schema | unit | `pytest sdg/scripts/test_validate_osft.py -x` | ❌ W0 | ⬜ pending |
| 04-0X-0X | TBD | TBD | D-13 (CR-01) | T-04-01 | `command_allowlist.yaml` enforced in `validate_command()` | unit | `cd mcp/mcp-telecom && uv run pytest tests/test_allowlist.py -x` | ✅ (needs rewrite) | ⬜ pending |
| 04-0X-0X | TBD | TBD | D-13 (CR-02) | T-04-02 | `show_interface_detail`'s interface argument sanitized | unit | `cd mcp/mcp-telecom && uv run pytest tests/test_interfaces.py -x` | ❌ W0 | ⬜ pending |
| 04-0X-0X | TBD | TBD | D-13 (CR-03) | T-04-03 | `compare_configs`' backup_file contained to `backups/` | unit | `cd mcp/mcp-telecom && uv run pytest tests/test_compare_configs.py -x` | ❌ W0 | ⬜ pending |
| 04-0X-0X | TBD | TBD | D-15 | — | NWDAF client speaks h2c to NextGCore | manual | Manual: curl test from pod | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*
*Plan/Wave/Task IDs are TBD — the planner fills these in once PLAN.md files are created.*

---

## Wave 0 Requirements

- [ ] `mcp/mcp-telecom/tests/test_allowlist.py` — rewrite to test production `validate_command()` instead of the current copy-pasted reimplementation (CR-01)
- [ ] `mcp/mcp-telecom/tests/test_interfaces.py` — new test for `show_interface_detail` argument sanitization (CR-02)
- [ ] `mcp/mcp-telecom/tests/test_compare_configs.py` — new test for `backup_file` path containment (CR-03)
- [ ] `sdg/scripts/test_serialize_osft.py` — validates OSFT JSONL serializer output, both trajectory formats (SDG-03, SDG-05)
- [ ] `sdg/scripts/test_validate_osft.py` — validates OSFT schema compliance inside `mcp_distillation_evaluation` (D-04, D-05)

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| sdg_hub pipeline generates traces end-to-end against the live MCP Gateway | SDG-01 | Requires live GPU-backed teacher model, live gateway, and live/simulated backends — not unit-testable | Run `01-dry-run.ipynb` on the OpenShift AI cluster; confirm traces are produced and traces route through the gateway |
| Curriculum ordering distribution (single-tool → closed-loop) | SDG-02 | Statistical/qualitative property of the full generation run, not a single assertion | Inspect generated example metadata; confirm all 5 curriculum tiers are represented with reasonable distribution |
| Quality filtering reduces 8.5K-14K raw to 5K-10K filtered | SDG-04 | Depends on full-scale generation run output, not reproducible in a unit test | Count rows in raw vs. filtered output after a full production run |
| OSFT dry-run validation with Farbod's team | D-19 | Requires Farbod's team's own training pipeline to confirm format compatibility — external dependency | Generate 10 examples, hand off to Farbod's team, confirm their mini-trainer/OSFT pipeline ingests them without error |
| NWDAF h2c live semantic verification | D-15 | Requires live NextGCore NWDAF endpoint, protocol-level behavior not mockable in pytest | `curl --http2-prior-knowledge` test from a pod against the NextGCore NWDAF endpoint, confirm valid analytics response |
| Containerlab topology device reachability | D-12, D-14 | Requires actual Containerlab deployment (network namespaces/privileged containers), not unit-testable | SSH/CLI round-trip to each Containerlab-provisioned device via MCP-Telecom's tools, confirm real (non-error) responses |
| Cross-cluster Keycloak client-credentials auth | D-07 | Requires two live clusters and a real token exchange | From the separate OpenShift AI cluster, fetch a JWT via Keycloak client-credentials grant and call the MCP Gateway Route, confirm 200 response |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s (automated tests); manual steps tracked separately
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
