---
phase: 03-mcp-domain-servers-and-gateway
reviewed: 2026-10-05T00:00:00Z
depth: standard
files_reviewed: 61
files_reviewed_list:
  - gateway/openshift/auth-policy.yaml
  - gateway/openshift/authorino-subscription.yaml
  - gateway/openshift/cert-manager-subscription.yaml
  - gateway/openshift/configure-keycloak.sh
  - gateway/openshift/gateway.yaml
  - gateway/openshift/httproute-camara.yaml
  - gateway/openshift/httproute-nwdaf.yaml
  - gateway/openshift/httproute-telecom.yaml
  - gateway/openshift/httproute-tmf621.yaml
  - gateway/openshift/httproute-tmf628.yaml
  - gateway/openshift/httproute-tmf642.yaml
  - gateway/openshift/istio-cni.yaml
  - gateway/openshift/istio.yaml
  - gateway/openshift/keycloak-subscription.yaml
  - gateway/openshift/keycloak.yaml
  - gateway/openshift/kuadrant.yaml
  - gateway/openshift/mcp-gateway-extension.yaml
  - gateway/openshift/mcp-gateway-subscription.yaml
  - gateway/openshift/mcpsr-camara.yaml
  - gateway/openshift/mcpsr-nwdaf.yaml
  - gateway/openshift/mcpsr-telecom.yaml
  - gateway/openshift/mcpsr-tmf621.yaml
  - gateway/openshift/mcpsr-tmf628.yaml
  - gateway/openshift/mcpsr-tmf642.yaml
  - gateway/openshift/mcpvs-camara.yaml
  - gateway/openshift/mcpvs-infra.yaml
  - gateway/openshift/mcpvs-nwdaf.yaml
  - gateway/openshift/mcpvs-tmf.yaml
  - gateway/openshift/namespace.yaml
  - gateway/openshift/ossm-subscription.yaml
  - gateway/openshift/reference-grant.yaml
  - gateway/openshift/rhcl-deps-subscription.yaml
  - mcp/camara/allowlist_retrieve.yaml
  - mcp/camara/allowlist_verify.yaml
  - mcp/camara/pyproject.toml
  - mcp/camara/server.py
  - mcp/camara/specs/camara_location_retrieval.yaml
  - mcp/camara/specs/camara_location_verification.yaml
  - mcp/nwdaf/allowlist_analytics.yaml
  - mcp/nwdaf/allowlist_events.yaml
  - mcp/nwdaf/pyproject.toml
  - mcp/nwdaf/server.py
  - mcp/nwdaf/specs/nwdaf_analyticsinfo_bundled.yaml
  - mcp/nwdaf/specs/nwdaf_eventssubscription_rel16.yaml
  - mcp/openshift/mcp-camara-deployment.yaml
  - mcp/openshift/mcp-nwdaf-deployment.yaml
  - mcp/openshift/mcp-tmf621-deployment.yaml
  - mcp/openshift/mcp-tmf628-deployment.yaml
  - mcp/openshift/mcp-tmf642-deployment.yaml
  - mcp/tmf621/allowlist.yaml
  - mcp/tmf621/pyproject.toml
  - mcp/tmf621/server.py
  - mcp/tmf628/allowlist.yaml
  - mcp/tmf628/pyproject.toml
  - mcp/tmf628/server.py
  - mcp/tmf642/allowlist.yaml
  - mcp/tmf642/pyproject.toml
  - mcp/tmf642/server.py
  - mcp/tooling/openapi_to_mcp.py
  - scripts/check-config.py
  - scripts/drift-check.sh
  - scripts/run-gateway-verify.sh
  - scripts/verify-domain-tools.sh
  - scripts/verify-gateway.sh
findings:
  critical: 2
  warning: 6
  info: 4
  total: 12
status: issues_found
---

# Phase 3: Code Review Report

**Reviewed:** 2026-10-05T00:00:00Z
**Depth:** standard
**Files Reviewed:** 61 (allowlist/data files `uv.lock` and raw OpenAPI spec YAML/JSON payloads excluded as non-reviewable generated/vendored data, per scope)
**Status:** issues_found

## Summary

Reviewed the 5 new FastMCP domain servers (tmf642, tmf628, tmf621, nwdaf, camara), the OpenShift/Gateway API manifests provisioning RHCL's MCP Gateway, the domain-server Deployment manifests, the `openapi_to_mcp.py` codegen tool, and the shell/Python verification scripts.

The most serious findings are two **live, git-committed credentials**: a real Keycloak OAuth2 client secret hardcoded in two verification scripts (and present in git history, not just the working tree), and a hardcoded Keycloak database password in a committed Kubernetes `Secret` manifest. Both should be treated as compromised and rotated regardless of whether the backing cluster is ephemeral.

Beyond secrets, the ConfigMap file-watcher pattern (BACK-03) that is supposed to be replicated identically across all 5 domain servers was **not** replicated identically — three servers (tmf642/628/621) start the polling thread as an unconditional side effect of module import and never consult an environment-variable fallback, while the other two (nwdaf/camara) defer thread startup to `create_app()` and support an env-var fallback. CAMARA's bearer-token auth headers are also hardcoded and have no live-switching mechanism, unlike the backend URL they're paired with, which partially defeats the purpose of the ConfigMap-driven mock→real backend cutover for that domain. Several lower-severity documentation/consistency issues round out the findings.

## Critical Issues

### CR-01: Live Keycloak client secret and test-user password hardcoded and committed to git

**File:** `scripts/drift-check.sh:8-9`, `scripts/run-gateway-verify.sh:8-9`

**Issue:** Both scripts hardcode a real, high-entropy Keycloak OAuth2 client secret and the gateway test-user password as literals:
```bash
CLIENT_SECRET="***REDACTED-CLIENT-SECRET***"
USER_PASSWORD="***REDACTED-PASSWORD***"
```
This is not a placeholder — `git log -p -- scripts/drift-check.sh` shows this exact secret was introduced in commit `c2d0f48` and is present in git history in two separate files. Combined with the hardcoded `GATEWAY_URL`/`KEYCLOAK_URL` pointing at a real, resolvable OpenShift sandbox hostname (`cluster-wfhjs.wfhjs.sandbox1330.opentlc.com`), anyone with read access to this repository (or its git history, even after a later "fix" commit) can authenticate to the live MCP Gateway and invoke tools through it. `configure-keycloak.sh` is capable of retrieving this secret dynamically (see `CR-02` context) — there is no reason the verification scripts need to hardcode it.

**Fix:** Rotate the Keycloak client secret and the `mcp-agent` user password on the live cluster immediately. Remove the literals from both scripts and source them from the environment or from the cluster at runtime, e.g.:
```bash
CLIENT_SECRET="${MCP_CLIENT_SECRET:?Set MCP_CLIENT_SECRET (do not hardcode)}"
USER_PASSWORD="${MCP_USER_PASSWORD:?Set MCP_USER_PASSWORD (do not hardcode)}"
# or: pull directly from the cluster
# CLIENT_SECRET=$(oc get secret keycloak-client-secret-mcp-gateway -n otel25-gateway -o jsonpath='{.data.CLIENT_SECRET}' | base64 -d)
```
Also consider scrubbing the secret from git history (e.g. `git filter-repo`) since rotation alone does not remove the historical exposure record.

### CR-02: Keycloak database password hardcoded in a committed Secret manifest

**File:** `gateway/openshift/keycloak.yaml:1-10`

**Issue:**
```yaml
apiVersion: v1
kind: Secret
metadata:
  name: keycloak-db-secret
  namespace: otel25-gateway
type: Opaque
stringData:
  username: keycloak
  password: ***REDACTED-DB-PASSWORD***
```
A Kubernetes `Secret` with a plaintext, low-entropy, hardcoded password is checked into version control. This password protects the PostgreSQL instance backing the entire Keycloak realm (which in turn issues the JWTs that gate access to the whole MCP Gateway). The "ephemeral / not production" comment does not mitigate the fact that this is a credential permanently recorded in git history, trivially guessable ("***REDACTED-DB-PASSWORD***"), and reused verbatim every time this manifest is applied.

**Fix:** Do not commit real or deterministic secret values. Generate the password at apply-time (e.g. `oc create secret generic keycloak-db-secret --from-literal=password=$(openssl rand -base64 24)`) or use a sealed-secrets/external-secrets mechanism, and reference a placeholder in the committed YAML:
```yaml
stringData:
  username: keycloak
  password: "{{ GENERATED_AT_DEPLOY_TIME }}"  # populated by deploy script, never committed
```

## Warnings

### WR-01: ConfigMap file-watcher (BACK-03) pattern is not replicated consistently across the 5 domain servers

**File:** `mcp/tmf642/server.py:192-194`, `mcp/tmf628/server.py:262-264`, `mcp/tmf621/server.py:114-116` vs. `mcp/nwdaf/server.py:200-207`, `mcp/camara/server.py:232-241`

**Issue:** The task description explicitly frames BACK-03 as a contract that must be identically replicated. It is not:
- tmf642/tmf628/tmf621 call `_load_backend_url()` and `_start_config_watcher()` unconditionally **at module import time** (top-level statements, not inside `create_app()`/`main()`/`if __name__ == "__main__"`). Merely importing `server.py` (e.g. from a test harness, a linter plugin, or the `openapi_to_mcp.py` tool for introspection) spins up a daemon thread that polls the filesystem every 5 seconds for the lifetime of the process — an import-time side effect with no way to opt out.
- nwdaf and camara instead start the watcher(s) inside `create_app()`, which only runs when the app is actually served — the safer pattern.
- Additionally, tmf642/628/621's fallback default is a hardcoded literal (`_backend_url = "http://localhost:4010"`) with **no environment-variable override**, whereas nwdaf/camara use `os.environ.get("NWDAF_BASE_URL", "http://localhost:4010")` / `os.environ.get("CAMARA_BASE_URL", "http://localhost:4010")`, allowing local-dev override without a ConfigMap file present.

This means the "same contract" was implemented three different ways across five servers that are supposed to share one pattern, and the TMF-family implementation has a real import-time side-effect anti-pattern.

**Fix:** Pick one canonical pattern (the nwdaf/camara one is better) and apply it to all 5 servers: move `_load_backend_url()`/`_start_config_watcher()` calls inside `create_app()`, and add an env-var fallback consistently, e.g.:
```python
_backend_url = os.environ.get("TMF642_BASE_URL", "http://localhost:4010")
...
def create_app():
    _load_backend_url()
    _start_config_watcher()
    ...
```

### WR-02: CAMARA auth header is hardcoded with no live-switching mechanism, unlike the backend URL it's paired with

**File:** `mcp/camara/server.py:148-154`

**Issue:**
```python
_CAMARA_AUTH_HEADERS = {"Authorization": "Bearer prism-mock-token"}
verify_client = httpx2.AsyncClient(base_url=get_verify_url(), headers=_CAMARA_AUTH_HEADERS)
retrieve_client = httpx2.AsyncClient(base_url=get_retrieve_url(), headers=_CAMARA_AUTH_HEADERS)
```
The whole point of the BACK-03 ConfigMap watcher is to let an operator repoint a domain server from the Prism mock to a real backend without a code change or redeploy. For CAMARA, the backend *URL* is live-switchable this way, but the *auth header* is a static Python literal baked in at process start with no ConfigMap/Secret/env-var equivalent. If an operator flips `CAMARA_BASE_URL`/`CAMARA_RETRIEVAL_BASE_URL` to a real CAMARA provider via the ConfigMap (exactly the supported, documented operation), every request will still carry the literal string `Bearer prism-mock-token`, which will simply fail auth against a real backend — silently, since nothing else changes. The comment acknowledges this is mock-only but provides no mechanism for the documented "switch to real backend" workflow to also supply real credentials.

**Fix:** Externalize the auth header the same way the backend URL is externalized (e.g. read a `CAMARA_AUTH_TOKEN` from a mounted Secret/ConfigMap, or make the header itself subject to the same file-watcher substitution), so that pointing CAMARA at a real backend doesn't require a code change in two places (URL vs. credential).

### WR-03: TMF642/628/621 MCPServerRegistration comments document a naming convention the code doesn't implement

**File:** `gateway/openshift/mcpsr-tmf642.yaml:2`, `mcpsr-tmf621.yaml:2`, `mcpsr-tmf628.yaml:2`, `mcpsr-nwdaf.yaml:2`, `mcpsr-camara.yaml:2`

**Issue:** All five `MCPServerRegistration` manifests contain a comment of the form `# Prefix "tmf642" -- all discovered tools prefixed with tmf642_ (e.g. tmf642_list_alarms)` (underscore-separated). The actual, verified tool-naming behavior (confirmed by `mcpvs-tmf.yaml`'s tool list, e.g. `tmf642listAlarm`, `tmf621createTroubleTicket`, `camararetrieve_location`, and explicitly called out in `scripts/verify-gateway.sh:45-46`: *"MCPServerRegistration prefix is concatenated without underscore (tmf642 + listAlarm)"*) is that the prefix is concatenated with **no separator**. This stale/incorrect comment appears identically in all 5 manifests and will mislead anyone writing a new `MCPVirtualServer` tool list or onboarding a 6th domain.

**Fix:** Correct the comment in all five files to match actual behavior, e.g.: `# Prefix "tmf642" -- concatenated directly with no separator (e.g. tmf642 + listAlarm -> tmf642listAlarm)`.

### WR-04: `curl -sk` (TLS verification disabled) used throughout `configure-keycloak.sh` with no justification or opt-out

**File:** `gateway/openshift/configure-keycloak.sh` (every `curl` invocation, e.g. lines 42, 57, 64, 77, 87, 107, 116, 123, 126, 148, 166, 175, 197)

**Issue:** Every request to the Keycloak admin API and token endpoint disables TLS certificate verification via `-k`. This is used to transmit the admin password, client secret, and user password over a connection whose server identity is never verified, making the script vulnerable to MITM credential interception if run against anything other than the exact intended cluster (e.g. a typo'd `NAMESPACE`/route lookup, a compromised DNS/proxy, or a different `KEYCLOAK_CR_NAME` resolving unexpectedly). There's no fallback to verified TLS even when the OpenShift router's default/self-signed CA is actually trustable.

**Fix:** At minimum, document why `-k` is required (likely a self-signed router cert) and scope the risk; prefer trusting the cluster's actual CA bundle (e.g. `curl --cacert <(oc get secret ... )`) over blanket `-k`, especially for calls that transmit the admin password and client secret.

### WR-05: Silent error-to-"not found" coercion in `configure-keycloak.sh` can mask API/auth failures as "resource doesn't exist"

**File:** `gateway/openshift/configure-keycloak.sh:81`, `:141`

**Issue:**
```bash
CLIENT_COUNT=$(echo "$EXISTING_CLIENTS" | python3 -c "import sys,json; print(len(json.load(sys.stdin)))" 2>/dev/null || echo "0")
```
If the preceding `curl` call fails for any reason other than "client truly doesn't exist" (expired admin token — note `accessTokenLifespan: 300` means a token obtained early in this multi-step script can expire if the script runs long — network blip, 5xx from Keycloak, malformed JSON), `EXISTING_CLIENTS` will not be a valid JSON list, `json.load` raises, and the `2>/dev/null || echo "0"` swallows that failure and reports `CLIENT_COUNT=0`. The script then proceeds down the "create it" branch using a possibly-expired/invalid admin token, producing confusing downstream failures or (worse) silently re-running creation logic against a transient error rather than failing loudly. The identical pattern exists for `USER_COUNT` at line 141.

**Fix:** Distinguish "valid empty list" from "request/parse failure" — e.g., capture the HTTP status code separately and fail fast on non-200, rather than coercing any parse failure to `"0"`.

### WR-06: Hardcoded `:latest` image tags in all 5 domain-server Deployments

**File:** `mcp/openshift/mcp-camara-deployment.yaml:24`, `mcp-nwdaf-deployment.yaml:24`, `mcp-tmf621-deployment.yaml:24`, `mcp-tmf628-deployment.yaml:24`, `mcp-tmf642-deployment.yaml:24`

**Issue:** All five Deployments pin `image: .../mcp-<domain>:latest`. Combined with the default `imagePullPolicy` (which OpenShift treats as `Always` for `:latest`), this makes deployments non-reproducible — a `kubectl rollout restart` or pod reschedule can pull a newer image than what was tested, and there is no way to correlate a running pod with the exact source commit that built it.

**Fix:** Tag images with a commit SHA or semantic version and reference that explicitly, e.g. `image: .../mcp-camara:0.1.0` or `:${GIT_SHA}`, updated by the build pipeline.

## Info

### IN-01: Unused `import json` in two domain servers

**File:** `mcp/tmf642/server.py:14`, `mcp/tmf621/server.py:13`

**Issue:** Both files `import json` at module scope but never reference `json.` anywhere in the file (confirmed via grep — only `tmf628/server.py`, which performs Swagger→OAS3 conversion, actually uses it). Dead import left over from template generation.

**Fix:** Remove the unused import, or if intentionally kept for template-consistency with `tmf628`, add a comment noting it's unused-but-templated.

### IN-02: Inconsistent dependency pins across sibling domain-server packages

**File:** `mcp/tmf642/pyproject.toml:14`, `mcp/tmf628/pyproject.toml:14`, `mcp/tmf621/pyproject.toml:14` (`uvicorn>=0.34.3`) vs. `mcp/nwdaf/pyproject.toml:10`, `mcp/camara/pyproject.toml:10` (`uvicorn>=0.30.0`)

**Issue:** Five packages generated from the same scaffold tool/template have drifted to two different minimum `uvicorn` versions with no apparent functional reason, and only `nwdaf`/`camara` declare a `[project.scripts]` console-script entry point (`mcp-nwdaf = "server:main"`) while `tmf642`/`tmf628`/`tmf621` do not. This is a minor but avoidable inconsistency across what should be a uniform set of sibling packages.

**Fix:** Align all 5 `pyproject.toml` files on the same minimum dependency versions and the same `[project.scripts]` convention, ideally by having `openapi_to_mcp.py`'s scaffold generation also emit the `pyproject.toml` so drift can't occur.

### IN-03: `scripts/check-config.py` has no error handling around `oc` invocation or secret decoding

**File:** `scripts/check-config.py:5-10`

**Issue:** `subprocess.run(...)` output is parsed with `json.loads(r.stdout)` without checking `r.returncode` first, and `d['data']['config.yaml']` is accessed without a `.get()`/try-except guard. If `oc get secret` fails (wrong context, RBAC, secret renamed), `r.stdout` will be empty or an error string, and `json.loads` will raise an unhandled `JSONDecodeError`/`KeyError` with a raw Python traceback instead of an actionable message — acceptable for an ad hoc debug script, but worth tightening since it's checked into the repo as a reusable tool.

**Fix:**
```python
if r.returncode != 0:
    print(f"ERROR: oc get secret failed: {r.stderr}", file=sys.stderr)
    sys.exit(1)
d = json.loads(r.stdout)
config_b64 = d.get('data', {}).get('config.yaml')
if not config_b64:
    print("ERROR: config.yaml key missing from secret", file=sys.stderr)
    sys.exit(1)
```

### IN-04: OLM Subscriptions default to `installPlanApproval: Automatic` across all operator installs

**File:** `gateway/openshift/mcp-gateway-subscription.yaml:24`, `rhcl-deps-subscription.yaml` (x3), `authorino-subscription.yaml:12`, `ossm-subscription.yaml:8`, `cert-manager-subscription.yaml:12`, `keycloak-subscription.yaml:19`

**Issue:** Every operator Subscription in this phase uses `installPlanApproval: Automatic`, meaning OLM will auto-upgrade these operators (including the RHCL/Kuadrant gateway stack that enforces authentication) without any manual review gate. For a gateway component whose job is auth enforcement, an unreviewed automatic upgrade is a higher-consequence event than for most workloads.

**Fix:** Consider `Manual` approval for the gateway/auth-critical operators (`mcp-gateway`, `rhcl-operator`, `authorino-operator`) so upgrades are reviewed before being applied, even if `Automatic` is acceptable for less security-sensitive dependencies.

---

_Reviewed: 2026-10-05T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
