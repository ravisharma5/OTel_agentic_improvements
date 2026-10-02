---
phase: 01-backend-infrastructure
fix_scope: critical_warning
findings_in_scope: 9
fixed: 7
skipped: 2
iteration: 1
status: partial
---

# Code Review Fix Report — Phase 1

> The code-fixer agent reported writing this file but it was never actually created on disk or committed (verified absent from git history and working tree). Reconstructed by the orchestrator from the agent's own completion report, cross-checked against the real commits below — all 7 commit hashes and messages were independently verified via `git log` before this report was written.

## Fixed (7/9)

| Finding | Commit | Files Modified | Live Cluster Verification |
|---------|--------|-----------------|---------------------------|
| CR-01: Missing UDM/UDR Services | `fb05e7a` | `backends/openshift/nextgcore/deployment-nextgcore.yaml` | DNS resolution confirmed for `udm` and `udr` services from within the cluster |
| CR-02: NWDAF self-advertised hostname mismatch | `38e2606` | `backends/openshift/nextgcore/configmap-nextgcore.yaml` | NWDAF pod restarted, confirmed Running 1/1 and TCP-reachable at `nextgcore-nwdaf:7777` |
| CR-03: `((counter++))` bash bug (set -e kills script on first increment under bash 4+/5+) | `6d5f20a` | `check-nwdaf.sh`, `validate-mocks.sh`, `verify-routing.sh` | All three scripts ran against the live cluster without dying on counter increments; `verify-routing.sh` completed all 6 key checks plus the ConfigMap switching contract demonstration (Step 2) |
| WR-01: `verify-routing.sh` treated any 2xx-4xx response as "OK" | `fa5840b` | `backends/scripts/verify-routing.sh` | Narrowed check to 2xx only |
| WR-02: `verify-routing.sh` always exited 0 regardless of failures | `d5ff832` | `backends/scripts/verify-routing.sh` | Now exits 1 on failure |
| WR-03: `nextgcore-upf` ServiceAccount referenced but never created | `6213b71` | `backends/openshift/nextgcore/scc-nextgcore-upf.yaml` | ServiceAccount applied declaratively via `oc apply`, confirmed present in cluster |
| WR-06: Bundled NWDAF spec missing provenance in SPEC_MANIFEST.md | `efeea4f` | `backends/specs/SPEC_MANIFEST.md` | N/A (documentation only) |

## Skipped (2/9) — with justification

- **WR-04** (only AMF has an exec-probe workaround for `NEXTGCORE_SBI_PROFILE=dev` despite every NF sharing the env var): Empirically verified that loopback SBI binding is AMF-specific — all other NFs run healthy with standard `tcpSocket` probes under the same dev-mode env var. Not a bug; no fix applied.
- **WR-05** (Prism NWDAF fallback/Path B specs vendored but never deployed as a Prism instance): This is a design/scope decision (whether to deploy an unused Path B Prism NWDAF instance alongside the now-live Path A NextGCore deployment), not a mechanical code fix. Requires human input — not auto-fixed.

## Not in scope (Info, not included in critical_warning fix scope)

- UPF SCC leaves root filesystem writable — Info-severity finding, excluded from this fix pass per `fix_scope: critical_warning` (would require `--all` to include).
