---
phase: 2
slug: mcp-tooling-foundation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-10-02
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >= 8.0 (project standard per STACK.md) |
| **Config file** | none — Wave 0 creates `mcp/mcp-telecom/pytest.ini` (or reuses upstream's existing config) |
| **Quick run command** | `cd mcp/mcp-telecom && uv run pytest tests/ -x --timeout=30` |
| **Full suite command** | `cd mcp/mcp-telecom && uv run pytest tests/ -v` |
| **Estimated runtime** | ~60 seconds (upstream has 157 tests) |

---

## Sampling Rate

- **After every task commit:** Run `cd mcp/mcp-telecom && uv run pytest tests/ -x --timeout=30`
- **After every plan wave:** Run full upstream test suite (`uv run pytest tests/ -v`) + verification scripts (`scripts/verify-mcp-telecom.sh`, conversion CLI smoke test)
- **Before `/gsd:verify-work`:** Full suite must be green, both verification scripts must pass
- **Max feedback latency:** 60 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| TBD | TBD | TBD | MCP-06a | T-02-01 | MCP-Telecom server starts with Streamable HTTP transport, no stdio fallback | smoke | `uv run python -c "from fastmcp import FastMCP; print('import ok')"` | ✅ | ⬜ pending |
| TBD | TBD | TBD | MCP-06b | — | MCP-Telecom's 58 tools register correctly after the fastmcp-package patch | unit | `cd mcp/mcp-telecom && uv run pytest tests/ -x` (upstream's 157 tests) | ✅ | ⬜ pending |
| TBD | TBD | TBD | MCP-06c | T-02-01 | `tools/list` returns the full tool catalog via Streamable HTTP | integration | `scripts/verify-mcp-telecom.sh` (D-08 verification) | ✅ W0 | ⬜ pending |
| TBD | TBD | TBD | MCP-06d | T-02-02 | One representative tool is invocable via MCP protocol (connection error acceptable — no device backend) | integration | `scripts/verify-mcp-telecom.sh` (D-08 verification) | ✅ W0 | ⬜ pending |
| TBD | TBD | TBD | MCP-07a | — | Conversion CLI generates a server.py scaffold from the CAMARA Device Location spec using the YAML allowlist | smoke | `cd mcp/tooling && uv run python openapi_to_mcp.py --spec ../../backends/specs/camara_location_verification.yaml --allowlist <config>` | ✅ W0 | ⬜ pending |
| TBD | TBD | TBD | MCP-07b | T-02-03 | Generated scaffold starts locally and lists its tools correctly (not deployed to OpenShift, per D-15) | smoke | `uv run python generated_server.py &; curl -X POST localhost:8000/mcp ...` (tools/list) | ✅ W0 | ⬜ pending |
| TBD | TBD | TBD | D-16 | T-02-04 | Generated scaffolds include file-watching for the mounted backend-routing ConfigMap (mtime-poll, not inotify) | unit | `pytest tests/test_configmap_watcher.py` | ✅ W0 | ⬜ pending |
| TBD | TBD | TBD | D-10a | T-02-05 | Safe-CLI-exec command allowlist scaffold rejects commands not on the (empty/placeholder) allowlist | unit | `pytest tests/test_allowlist.py` | ✅ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `mcp/mcp-telecom/pytest.ini` — configure pytest for the vendored copy (may reuse upstream's existing config)
- [ ] `scripts/verify-mcp-telecom.sh` — covers MCP-06c, MCP-06d (D-08 verification: tools/list + one sample call)
- [ ] Smoke test script/commands for the conversion CLI (MCP-07a, MCP-07b) — local-only per D-15, no OpenShift deploy
- [ ] `tests/test_configmap_watcher.py` — covers D-16's mtime-polling file-watcher (inotify breaks on ConfigMap symlink swaps per research)
- [ ] `tests/test_allowlist.py` — covers D-10a's command-allowlist scaffold

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|--------------------|
| MCP-Telecom deployed and reachable in the `otel25-mcp` OpenShift namespace | MCP-06 | Requires live cluster access (`oc` CLI), not reproducible in CI/local test run | `oc get pods -n otel25-mcp`, then run `scripts/verify-mcp-telecom.sh` against the in-cluster Service URL |
| OpenShift readiness/liveness probes pass post-deploy | MCP-06 | Requires the Deployment to be live on cluster; probe behavior can't be unit tested | `oc describe pod -n otel25-mcp <mcp-telecom-pod>` — confirm no probe failures in events |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 60s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
