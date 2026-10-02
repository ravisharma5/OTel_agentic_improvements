---
phase: 01-backend-infrastructure
reviewed: 2026-10-02T00:00:00Z
depth: standard
files_reviewed: 25
files_reviewed_list:
  - backends/openshift/configmap-backend-routing.yaml
  - backends/openshift/namespace.yaml
  - backends/openshift/nextgcore/configmap-nextgcore.yaml
  - backends/openshift/nextgcore/deployment-nextgcore.yaml
  - backends/openshift/nextgcore/Dockerfile.runtime
  - backends/openshift/nextgcore/scc-nextgcore-upf.yaml
  - backends/openshift/nextgcore/service-nwdaf.yaml
  - backends/openshift/prism-camara-retrieval.yaml
  - backends/openshift/prism-camara.yaml
  - backends/openshift/prism-tmf621.yaml
  - backends/openshift/prism-tmf628.yaml
  - backends/openshift/prism-tmf642.yaml
  - backends/prism/Dockerfile
  - backends/scripts/check-nwdaf.sh
  - backends/scripts/validate-mocks.sh
  - backends/scripts/verify-routing.sh
  - backends/specs/camara_location_retrieval.yaml
  - backends/specs/camara_location_verification.yaml
  - backends/specs/nwdaf_analyticsinfo_bundled.yaml
  - backends/specs/nwdaf_analyticsinfo_rel16.yaml
  - backends/specs/nwdaf_eventssubscription_rel16.yaml
  - backends/specs/SPEC_MANIFEST.md
  - backends/specs/tmf621_troubleticket_v5.0.1.oas.yaml
  - backends/specs/tmf628_performance_v4.0.0.swagger.json
  - backends/specs/tmf642_alarm_v5.0.1.oas.yaml
findings:
  critical: 3
  warning: 6
  info: 1
  total: 10
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-10-02T00:00:00Z
**Depth:** standard
**Files Reviewed:** 25
**Status:** issues_found

## Summary

Reviewed the Phase 1 backend infrastructure: OpenShift manifests for the NextGCore 5G-core NF mesh (Path A, real NWDAF), the five Prism mock backends (Path B), the backend-routing ConfigMap, and the three shell verification/validation scripts, plus vendored OpenAPI specs.

Two concrete Kubernetes manifest defects were found that will break NF-to-NF reachability inside the NextGCore mesh (missing Services for UDM/UDR, and a hostname mismatch between NWDAF's self-advertised SBI address and its actual Service name). More seriously, all three shell scripts (`check-nwdaf.sh`, `validate-mocks.sh`, `verify-routing.sh`) share a `set -euo pipefail` + `((counter++))` bug that I reproduced empirically with Bash 5.3: the first time any counter goes from `0` to `1`, the arithmetic expression evaluates to `0` (falsy), `set -e` treats that as a command failure, and the script terminates immediately and silently. This means none of the three scripts can complete their validation loops as written — `verify-routing.sh` in particular dies right after checking the very first routing key and never reaches its own stated purpose (Step 2: demonstrating the ConfigMap switching contract, BACK-03).

I also empirically ran the real `stoplight/prism-cli` mock server against the vendored `tmf628_performance_v4.0.0.swagger.json` spec to verify the Swagger-2.0 `basePath` handling assumption built into the readiness probes and `validate-mocks.sh` — Prism serves the bare path (`/measurementCollectionJob`, HTTP 200) and does **not** prepend `basePath`, confirming the probes/paths in `prism-tmf628.yaml` and `validate-mocks.sh` are correct as written.

## Critical Issues

### CR-01: UDM and UDR Deployments have no matching Service

**File:** `backends/openshift/nextgcore/deployment-nextgcore.yaml:269-406`
**Issue:** Every NextGCore NF Deployment in this file (`nrf`, `ausf`, `amf`, `smf`, `upf`, `nwdaf`) is immediately followed by a matching `Service` object providing a stable `*.otel25-backends.svc.cluster.local` DNS name. The `udm` Deployment (lines 269-335) and `udr` Deployment (lines 339-406) are the only two NFs in the mesh with no corresponding `Service`. Confirmed via `grep -n "kind: Service\|kind: Deployment"` — there are 8 `Deployment` blocks but only 6 `Service` blocks, and the two missing ones are exactly `udm`/`udr`.

Without a Service, these two NFs have no stable cluster DNS name and no explicit Endpoints/ClusterIP; any NF or tooling that needs to reach UDM/UDR by name (standard 3GPP discovery via NRF, or manual `oc exec curl` debugging) cannot do so, and the address becomes unstable across pod reschedules. This breaks the authentication/subscriber-data chain (AUSF→UDM→UDR) that real UE attach/NWDAF-load-generation flows depend on.

**Fix:** Add `Service` objects for `udm` and `udr`, mirroring the pattern used for `ausf`/`nrf` (ClusterIP, port 7777 named `sbi`):
```yaml
---
apiVersion: v1
kind: Service
metadata:
  name: udm
  namespace: otel25-backends
  labels:
    app.kubernetes.io/name: udm
    app.kubernetes.io/part-of: nextgcore
spec:
  selector:
    app.kubernetes.io/name: udm
  ports:
    - name: sbi
      port: 7777
      targetPort: 7777
  type: ClusterIP
```
(repeat for `udr`)

### CR-02: NWDAF advertises a hostname that does not match its actual Service name

**File:** `backends/openshift/nextgcore/configmap-nextgcore.yaml:225` and `backends/openshift/nextgcore/service-nwdaf.yaml:11`
**Issue:** `nwdaf.yaml` in the ConfigMap configures `sbi.server[0].advertise: nwdaf.otel25-backends.svc.cluster.local` (line 225) — this is the hostname NWDAF registers with NRF so other NFs can reach it. The only `Service` that actually targets the NWDAF pods (`app.kubernetes.io/name: nwdaf` selector) is named `nextgcore-nwdaf` (`service-nwdaf.yaml:11`), not `nwdaf`. `nwdaf.otel25-backends.svc.cluster.local` does not exist as a Service/Endpoints object anywhere in the manifests (confirmed via grep across both files), so it will not resolve in-cluster.

Any NF that discovers NWDAF dynamically via NRF (the standard SBI discovery flow this ConfigMap's own `nrf.yaml`/`ausf.yaml`/etc. rely on for every other link) will receive an unroutable hostname and fail to connect. The external-facing `backend-routing` ConfigMap happens to use the correct `nextgcore-nwdaf` name, which masks this bug for the MCP-server consumption path but not for internal 5GC NF-to-NF SBI calls.

**Fix:** Make the advertised name match the real Service, either by renaming the Service to `nwdaf` (and updating `backend-routing`'s comment/consumers accordingly) or, preferably, by fixing the advertise value to match the existing Service:
```yaml
  nwdaf.yaml: |
    ...
    nwdaf:
      sbi:
        server:
          - address: 0.0.0.0
            advertise: nextgcore-nwdaf.otel25-backends.svc.cluster.local
            port: 7777
```

### CR-03: `set -euo pipefail` combined with `((counter++))` silently kills all three shell scripts on the first increment

**Files:**
- `backends/scripts/check-nwdaf.sh:78,85,88,94,97,103,106`
- `backends/scripts/validate-mocks.sh:31-33,148,158,165,167,168`
- `backends/scripts/verify-routing.sh:33-34,40,60,63`

**Issue:** All three scripts start counters at `0` (e.g. `PASS=0`, `FAIL=0`, `ANALYTICS_FIELDS_CHECKED=0`) and increment them with the post-increment arithmetic command `((VAR++))`, under `set -euo pipefail`. In Bash, `((expr))` returns exit status 1 when `expr` evaluates to `0`; `i++` (post-increment) evaluates to the value of `i` *before* incrementing. So the very first time any of these counters goes from `0` to `1`, the command itself returns exit status 1, and `set -e` terminates the script immediately — silently, with no error message, because it isn't inside a conditional/`&&`/`||` context that `set -e` exempts.

I verified this is not theoretical: I reproduced it with Bash 5.3.20 (the version virtually any Linux/CI/OpenShift container will have — macOS's bundled Bash 3.2 happens not to trigger it, which likely explains why this slipped through local testing) using a minimal repro of each script's loop structure:
```
$ bash /tmp/test_verify.sh   # loop structure copied from verify-routing.sh
iter 1
  OK
exit: 1        # script died after the FIRST ((PASS++)), never reached iter 2 or 3
```

Concrete impact per script:
- `verify-routing.sh`: dies right after printing `OK` for the very first routing key (line 60, first `((PASS++))`). It never checks the remaining 5 keys and — critically — never reaches "Step 2: Verify ConfigMap switching contract" (lines 76-109), which is the script's actual stated purpose (demonstrating BACK-03/D-16 live switching). The script's own "always exit 0" bug (see WR-02) further hides this failure from callers.
- `validate-mocks.sh`: dies after validating at most one endpoint (first `((FAIL++))` at line 148 on a failure, or first `((PASS++))`/`((WARN++))` at lines 165-168 on a pass), never producing the "=== Results ===" summary for the remaining 4 endpoints.
- `check-nwdaf.sh`: dies on the very first loop iteration at line 85 (`((ANALYTICS_FIELDS_CHECKED++))`, the first statement in the `for field in sliceLoadLevelInfos...` loop), before any field is actually checked, and never reaches the intended `exit 0` at line 127.

**Fix:** Use a form that doesn't return a falsy/zero exit status on the eventful transition, e.g. pre-increment, arithmetic expansion, or explicitly discard the status:
```bash
# any of these avoid the set -e trap:
: $((VAR++))
VAR=$((VAR + 1))
((VAR += 1)) || true
```
Apply this to every `((...++))` occurrence in all three scripts.

## Warnings

### WR-01: `verify-routing.sh` treats 4xx responses as "OK", contradicting its own stated verification goal

**File:** `backends/scripts/verify-routing.sh:58`
**Issue:** The header comment (lines 1-9) says the script "curls each URL, verifies 2xx responses," but the actual check is `if [[ "$HTTP_CODE" =~ ^[2-4] ]]; then echo "  OK ($HTTP_CODE)"`. This accepts any HTTP code starting with 2, 3, or 4 as "OK" — including 404 Not Found and 401 Unauthorized. For `CAMARA_BASE_URL`/`CAMARA_RETRIEVAL_BASE_URL`, the test path is `/` (line 51-52), which will almost always 404 against a Prism mock (no operation defined at `/`), so this will routinely report "OK" for a path that proves nothing about actual backend health.
**Fix:** Either narrow the regex to `^2` to match the documented intent, or explicitly document/accept that 4xx means "reachable but needs a valid path/auth" as a distinct status rather than folding it into "OK".

### WR-02: `verify-routing.sh` always exits 0, even when checks fail

**File:** `backends/scripts/verify-routing.sh:112-119`
**Issue:** At the end of the script, both branches of `if [[ $FAIL -eq 0 ]]` print "OVERALL: PASS" (just with different wording) and both call `exit 0`. This means the script can never signal failure via its exit code, so CI pipelines or wrapper tooling cannot detect a routing/connectivity problem by checking `$?`. This is inconsistent with `validate-mocks.sh`, which correctly `exit 1`s on failure.
**Fix:**
```bash
if [[ $FAIL -eq 0 ]]; then
  echo "OVERALL: PASS"
  exit 0
else
  echo "OVERALL: FAIL ($FAIL backend(s) unreachable)"
  exit 1
fi
```

### WR-03: `serviceAccountName: nextgcore-upf` is referenced but never created

**File:** `backends/openshift/nextgcore/deployment-nextgcore.yaml:614`
**Issue:** The `upf` pod spec sets `serviceAccountName: nextgcore-upf`, and `scc-nextgcore-upf.yaml` grants SCC permissions to `system:serviceaccount:otel25-backends:nextgcore-upf` (line 58), but no `kind: ServiceAccount` resource exists anywhere in the reviewed manifest set (confirmed via `grep -rn "kind: ServiceAccount"` across all `backends/openshift/**/*.yaml` — zero matches). If the ServiceAccount isn't created out-of-band (e.g. via an undocumented `oc create sa` step), the Deployment will fail admission with "serviceaccount nextgcore-upf not found."
**Fix:** Add the ServiceAccount manifest alongside the SCC:
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: nextgcore-upf
  namespace: otel25-backends
```

### WR-04: `NEXTGCORE_SBI_PROFILE: dev` is set on every NF, but only AMF has the loopback-binding probe workaround

**File:** `backends/openshift/nextgcore/deployment-nextgcore.yaml:464-475` (AMF) vs. `nrf`, `ausf`, `udm`, `udr`, `smf`, `nwdaf` (all set the identical `NEXTGCORE_SBI_PROFILE: dev` env var at lines 127-128, 215-216, 303-304, 374-375, 541-542, 737-738)
**Issue:** The AMF container has an explicit comment and workaround: "AMF binds SBI to 127.0.0.1 in dev mode, so tcpSocket probe ... fails. Use exec probe instead" (lines 464-465), replacing the readiness/liveness probes with an `exec` probe that falls back to `ss -tln`. Every other NF in the file sets the exact same `NEXTGCORE_SBI_PROFILE: dev` value but keeps a plain `tcpSocket` probe. If "dev" profile causes the same loopback-only SBI binding behavior in NRF/AUSF/UDM/UDR/SMF/NWDAF as it does in AMF, their `tcpSocket` probes (and the `wait-nrf` init containers on every downstream Deployment, which do `nc -z nrf...:7777`) would never succeed, and the entire mesh would deadlock waiting on NRF readiness. If this really is AMF-specific, that's fine, but nothing in the file documents why AMF differs from the rest despite identical configuration.
**Fix:** Verify empirically whether `nrf`/`ausf`/`udm`/`udr`/`smf`/`nwdaf` also bind SBI to loopback under `NEXTGCORE_SBI_PROFILE=dev`; if so, apply the same exec-probe workaround to all of them, and document the actual root cause (e.g. is it NGAP-related and AMF-only, or truly a global "dev profile" behavior).

### WR-05: Vendored NWDAF specs for Prism "Path B" are unused in this manifest set — fallback path appears undocumented/unimplemented

**File:** `backends/specs/nwdaf_analyticsinfo_bundled.yaml`, `backends/specs/nwdaf_analyticsinfo_rel16.yaml`, `backends/specs/nwdaf_eventssubscription_rel16.yaml`
**Issue:** `configmap-backend-routing.yaml` and `check-nwdaf.sh` both describe a "Path B (Prism mock)" fallback for NWDAF (per decision D-10: "If NWDAF is consistently failing, consider fallback to Prism mock per D-10"), and three NWDAF-related specs are vendored specifically for this. However, there is no `prism-nwdaf.yaml` OpenShift manifest and no Dockerfile build step in the reviewed files that actually builds/deploys a Prism container for any of these three specs (confirmed via `grep -rn "analyticsinfo\|eventssubscription" backends/openshift backends/scripts backends/prism` — only path-string references, no deployment/build artifact). Either the fallback path is incomplete, or these three spec files are dead weight carried into the repo without a consumer.
**Fix:** Either add the missing `prism-nwdaf` Deployment/Service/Dockerfile build (mirroring the other 5 Prism backends) to make Path B actually deployable, or remove/clearly mark the unused specs and update the D-10 fallback language to reflect that it is aspirational/manual rather than a ready-to-switch deployment.

### WR-06: `SPEC_MANIFEST.md` omits provenance for the bundled NWDAF spec actually referenced by Path B tooling

**File:** `backends/specs/SPEC_MANIFEST.md:7-23`
**Issue:** The manifest table tracks `nwdaf_analyticsinfo_rel16.yaml` and `nwdaf_eventssubscription_rel16.yaml` (the raw, un-bundled specs) but has no entry for `nwdaf_analyticsinfo_bundled.yaml`, which is the file whose header (`backends/specs/nwdaf_analyticsinfo_bundled.yaml:1-11`) states it is the actual "Self-contained bundle for Prism mock server" — i.e., the one meant to be baked into a Prism image per D-06. Without a manifest entry, there's no recorded provenance/pinning for how the inlined `$ref`s were generated or whether they're kept in sync with the rel16 source.
**Fix:** Add a manifest row for the bundled spec noting it is derived from `nwdaf_analyticsinfo_rel16.yaml` (+ referenced external schemas), and how/when it was regenerated.

## Info

### IN-01: UPF SCC leaves the root filesystem writable

**File:** `backends/openshift/nextgcore/scc-nextgcore-upf.yaml:40`
**Issue:** `readOnlyRootFilesystem: false` combined with `allowPrivilegedContainer: true` and `allowHostDirVolumePlugin: true` gives the UPF container a fairly broad attack surface. The threat-model comment at the top of the file (T-04-01) addresses privilege escalation via SA scoping and pod isolation but doesn't address root-FS write access specifically.
**Fix:** If the `nextgcore-upfd` binary only needs to write to `/var/log/nextgcore` and `/var/lib/nextgcore` (already covered by the `emptyDir` volumes in the Deployment), consider setting `readOnlyRootFilesystem: true` on the SCC/pod and relying on the existing volume mounts for writable paths.

---

_Reviewed: 2026-10-02T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
