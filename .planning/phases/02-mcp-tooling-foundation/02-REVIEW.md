---
phase: 02-mcp-tooling-foundation
reviewed: 2026-10-04T18:51:35Z
depth: standard
files_reviewed: 21
files_reviewed_list:
  - mcp/mcp-telecom/command_allowlist.yaml
  - mcp/mcp-telecom/devices.yaml.example
  - mcp/mcp-telecom/Dockerfile
  - mcp/mcp-telecom/pyproject.toml
  - mcp/mcp-telecom/src/mcp_telecom/server.py
  - mcp/mcp-telecom/tests/test_allowlist.py
  - mcp/mcp-telecom/uv.lock
  - mcp/openshift/mcp-telecom-deployment.yaml
  - mcp/openshift/mcp-telecom-secret.yaml
  - mcp/openshift/namespace.yaml
  - mcp/tooling/allowlist_schema.py
  - mcp/tooling/openapi_to_mcp.py
  - mcp/tooling/pyproject.toml
  - mcp/tooling/tests/__init__.py
  - mcp/tooling/tests/camara_allowlist.yaml
  - mcp/tooling/tests/synthetic_allowlist.yaml
  - mcp/tooling/tests/synthetic_two_op_spec.yaml
  - mcp/tooling/tests/test_allowlist_filtering.py
  - mcp/tooling/tests/test_configmap_watcher.py
  - mcp/tooling/uv.lock
  - scripts/verify-mcp-telecom.sh
findings:
  critical: 3
  warning: 6
  info: 4
  total: 13
  false_positives_removed: 1
status: issues_found
verified_by: orchestrator
verification_note: "CR-04 (httpx2 ModuleNotFoundError) independently re-tested by the orchestrator and disproven — see note below CR-04. CR-01/02/03 independently confirmed by direct source inspection."
---

# Phase 02: Code Review Report

**Reviewed:** 2026-10-04T18:51:35Z
**Depth:** standard
**Files Reviewed:** 21
**Status:** issues_found

## Summary

Reviewed the MCP-Telecom server (vendored FastMCP tool server for network devices), the
`mcp/tooling` OpenAPI-to-MCP scaffold generator, their test suites, and the OpenShift
deployment manifests for Phase 02.

Two classes of problems dominate:

1. **A documented security control that is never enforced.** `command_allowlist.yaml`
   advertises a "deny-by-default" guarantee for the `run_command` tool, and
   `tests/test_allowlist.py` exercises that guarantee — but the guarantee is checked
   against a copy of the logic pasted into the test file, not against any code path the
   server actually executes. `server.py`'s `run_command` tool, and every other
   vendor-mapped tool, never load or consult `command_allowlist.yaml`. The file and its
   test give a false sense of enforced policy.

2. **Unsanitized user input reaching device CLI sessions and the local filesystem.**
   `show_interface_detail`'s `interface` argument is formatted directly into a vendor CLI
   command template and sent to the device over SSH with no validation and no safety-gate
   call, unlike `run_command`. `compare_configs`'s `backup_file` argument is passed
   straight to `Path(...).read_text()` with no containment, allowing arbitrary local file
   disclosure.

Additionally, the `mcp/tooling/openapi_to_mcp.py` scaffold generator emits
`import httpx2` / `httpx2.AsyncClient(...)` in every generated server — a typo that
breaks every scaffold produced by the tool (`ModuleNotFoundError: No module named 'httpx2'`),
which would also be expected to fail `test_allowlist_filtering.py`'s dynamic subprocess
check once `fastmcp`/`httpx` dependencies are actually installed in the test environment.

## Critical Issues

> **Orchestrator verification note (CR-01, CR-02, CR-03):** All three independently confirmed true by direct source inspection (`grep` for `command_allowlist`/`allowed_commands` outside `tests/` returns no hits in `src/`; `show_interface_detail` and `compare_configs` read directly off `server.py`). Exploitability today is bounded by D-07 (no real device backend wired in Phase 2 — `devices.yaml` has only the placeholder example host) — CR-02 and CR-03 both require a successful `device_manager.connect(device)` before reaching the vulnerable line, which will fail against the placeholder device. **CR-01 is the exception: `validate_command()` runs *before* any device connection, so the validation-layer gap is observable today**, even though no command actually reaches a real device. All three become live risks the moment Phase 4 wires a real device without first fixing them — they should not wait until Phase 4 is underway to address, since by then MCP-Telecom will already be exposed to an LLM agent with real device access.

### CR-01: Deny-by-default command allowlist is never loaded by the server

**File:** `mcp/mcp-telecom/command_allowlist.yaml:1-29`, `mcp/mcp-telecom/src/mcp_telecom/server.py:505-530`, `mcp/mcp-telecom/tests/test_allowlist.py:18-43`

**Issue:** `command_allowlist.yaml`'s header states: *"When the `allowed_commands` list is
empty, ALL CLI commands submitted through the safe-exec tool (`run_command`) are
rejected."* This is false as implemented. `server.py`'s `run_command` tool (lines
505-530) only calls `validate_command()` from `mcp_telecom.safety`, which is a
regex-based allow-prefix/block-pattern check (`src/mcp_telecom/safety.py`) that has no
knowledge of `command_allowlist.yaml` or its `allowed_commands` list:

```
$ grep -rn "command_allowlist\|allowed_commands" src/ tests/
tests/test_allowlist.py:30:    return data.get("allowed_commands", []) or []
tests/test_allowlist.py:67:            Path(__file__).parent.parent / "command_allowlist.yaml"
...
```

No hit outside `tests/`. `test_allowlist.py` does not import any production module —
it reimplements `load_allowlist()` and `check_command_allowed()` locally (lines 18-43)
and tests that local copy. The tests pass, but they validate dead code, not the actual
`run_command` request path. As shipped, with the default empty `allowed_commands: []`,
`run_command("show bgp summary", ...)` **succeeds** (allowed by `safety.py`'s
`ALLOWED_PREFIXES`), directly contradicting the documented deny-by-default guarantee.

**Fix:** Either wire the allowlist into `safety.validate_command()` (load
`command_allowlist.yaml` once at startup, and additionally require
`check_command_allowed(command, allowlist)` to pass before `is_safe_command`), and have
`test_allowlist.py` import that real implementation instead of a local copy — or remove
the file/tests and correct the docstring in `run_command` if allowlist enforcement is
intentionally deferred to Phase 4 (in which case the "DENY-BY-DEFAULT SAFETY MECHANISM"
claim in the YAML header must be rewritten to say it is not yet enforced).

```python
# safety.py
_ALLOWLIST_PATH = os.getenv("MCP_TELECOM_ALLOWLIST_FILE", "command_allowlist.yaml")

def load_allowlist(path: str = _ALLOWLIST_PATH) -> list[str]:
    p = Path(path)
    if not p.exists():
        return []
    data = yaml.safe_load(p.read_text()) or {}
    return data.get("allowed_commands") or []

def validate_command(command: str, allowlist: list[str] | None = None) -> str | None:
    ...
    allowlist = allowlist if allowlist is not None else load_allowlist()
    if not any(cmd.lower().startswith(p.lower()) for p in allowlist):
        return "Command blocked: not present in command_allowlist.yaml"
    ...
```

---

### CR-02: Unsanitized `interface` argument injected into device CLI command, bypassing all safety checks

**File:** `mcp/mcp-telecom/src/mcp_telecom/server.py:183-203` (uses `mcp/mcp-telecom/src/mcp_telecom/vendors/mappings.py:204-234`)

**Issue:** `show_interface_detail(device, interface)` builds the command with:

```python
cmd = get_command(config.device_type, "interface_detail", interface=interface)
with device_manager.connect(device) as conn:
    output = conn.send_command(cmd)
```

`get_command()` does `template.format(**kwargs)` (mappings.py:234) with no sanitization
of `interface`, and `show_interface_detail` never calls `validate_command()` (that gate
is only applied inside the generic `run_command` tool, lines 505-530). An `interface`
value containing embedded newlines or CLI metacharacters (e.g.
`"Gi0/0/0\nconfigure terminal\nno shutdown Gi0/1"`) is formatted straight into the
command string and written to the live SSH session via netmiko's `send_command`
(`connection.py` yields the raw `ConnectHandler`), which will interpret embedded
newlines as additional Enter-terminated command lines on the device. This lets a caller
(or a prompt-injected AI agent) issue arbitrary configuration commands through a tool
that is documented and named as read-only, completely bypassing the one safety check
(`validate_command`) that exists in this codebase.

**Fix:** Validate `interface` against an allow-pattern before formatting, and/or route
all templated commands through `validate_command()` as well:

```python
import re
_INTERFACE_RE = re.compile(r"^[A-Za-z0-9_./:-]+$")

def show_interface_detail(device: str, interface: str) -> str:
    if not _INTERFACE_RE.fullmatch(interface):
        return f"Error: invalid interface name: {interface!r}"
    ...
```

---

### CR-03: Arbitrary local file read via `compare_configs`' `backup_file` parameter

**File:** `mcp/mcp-telecom/src/mcp_telecom/server.py:461-500` (specifically lines 481-485)

**Issue:**

```python
backup_path = Path(backup_file)
if not backup_path.exists():
    return f"Error: Backup file not found: {backup_file}"
previous = backup_path.read_text()
```

`backup_file` is a free-form string supplied directly to the MCP tool call with no
containment to the `backups/` directory that `backup_config()` writes to
(`src/mcp_telecom/tools/system.py:95-101`). Any path reachable by the server process —
e.g. `/app/devices.yaml` (containing the `credential_secret_ref`), `/etc/passwd`, or any
other file inside the container — can be read and returned to the caller as part of the
diff output. Since this is exposed as an MCP tool to an LLM agent, this is exploitable
either directly or via prompt injection to exfiltrate local files.

**Fix:** Resolve `backup_file` against a fixed backups directory and reject paths that
escape it:

```python
BACKUPS_DIR = Path("backups").resolve()

def compare_configs(device: str, backup_file: str) -> str:
    candidate = (BACKUPS_DIR / Path(backup_file).name).resolve()
    if not candidate.is_relative_to(BACKUPS_DIR) or not candidate.exists():
        return f"Error: Backup file not found: {backup_file}"
    previous = candidate.read_text()
    ...
```

---

### ~~CR-04: `import httpx2` typo breaks every scaffold generated by `openapi_to_mcp.py`~~ — FALSE POSITIVE, DISPROVEN

> **Orchestrator verification:** This finding is incorrect and does not apply. The reviewer's sandbox did not have `fastmcp` installed and inferred `httpx2` was a hallucinated/typo'd module name without executing anything. `httpx2` is a real, independently-maintained PyPI package (v2.13.1) and a **declared dependency of `fastmcp-slim`** (the real package backing `fastmcp>=4.0.0`) — `uv lock` resolves it automatically into `mcp/tooling/uv.lock`. Verified directly:
> - `uv run python -c "import httpx2"` succeeds in `mcp/tooling`'s own venv (`httpx2.__file__` resolves to an installed package).
> - A scaffold was generated against the real CAMARA spec (`uv run python openapi_to_mcp.py --spec ../../backends/specs/camara_location_verification.yaml ...`) and run directly: it started cleanly, logged `Uvicorn running on http://0.0.0.0:8000`, with **no `ModuleNotFoundError`**.
> - `uv run pytest tests/` in `mcp/tooling` passes all 5 tests, including `test_allowlist_filtering.py`'s dynamic subprocess check that starts a generated scaffold and calls `tools/list` against it — the exact path this finding claimed would fail.
>
> (Interesting footnote: `slopcheck` — a dedicated AI-hallucinated-package detector — also flagged `httpx2` as `[SUS]` on the same "looks like a typo" heuristic, and that too was a false positive on manual verification during Plan 02-01. Two independent tools made the same name-pattern mistake; worth remembering that `httpx2` is legitimate in this codebase.)

<details>
<summary>Original (incorrect) finding, kept for record</summary>

**File:** `mcp/tooling/openapi_to_mcp.py:56, 143`

**Issue:** The generated-server template imports and instantiates a nonexistent module:

```python
import httpx2
...
client = httpx2.AsyncClient(base_url=get_backend_url())
```

Every server generated by this CLI would fail at import time with
`ModuleNotFoundError: No module named 'httpx2'` — claimed but not actually true.

</details>

## Warnings

### WR-01: OpenShift Deployment never mounts the device-credentials Secret

**File:** `mcp/openshift/mcp-telecom-deployment.yaml:20-43`, `mcp/mcp-telecom/devices.yaml.example:7-28`

**Issue:** `devices.yaml.example` documents: *"When deployed on OpenShift, the Secret's
keys are mounted as environment variables or files inside the pod... The Deployment
manifest mounts this Secret and the server reads credentials from the corresponding
environment variables at runtime."* The actual `mcp-telecom` container spec has no
`env`, `envFrom`, or `volumeMounts` referencing `mcp-telecom-device-creds` (or any
secret) at all. If this is intentionally deferred to Phase 4, the comment in
`devices.yaml.example` overstates current behavior and will mislead whoever wires real
devices later into assuming the plumbing already exists.

**Fix:** Either add the `envFrom`/`volumeMounts` wiring now (even if the Secret is a
placeholder), or soften the `devices.yaml.example` comment to state this mounting is not
yet implemented in the current Deployment manifest.

### WR-02: Secret key names don't match documented per-vendor key naming

**File:** `mcp/openshift/mcp-telecom-secret.yaml:12-14`, `mcp/mcp-telecom/devices.yaml.example:21-25`

**Issue:** `devices.yaml.example`'s example Secret shows per-vendor keys
(`NOKIA_USERNAME`, `NOKIA_PASSWORD`, `CISCO_USERNAME`, `CISCO_PASSWORD`), but the actual
committed `mcp-telecom-secret.yaml` defines generic `device_username` / `device_password`
keys. Whoever implements Phase 4 credential wiring will hit an inconsistency between the
documented contract and the deployed Secret shape.

**Fix:** Align the two — pick one naming convention (generic vs. per-vendor) and update
both files to match before Phase 4 consumes them.

### WR-03: Pervasive duplicated try/except/audit boilerplate across ~25 tool functions

**File:** `mcp/mcp-telecom/src/mcp_telecom/server.py` (e.g. lines 53-73, 75-94, 97-115, 118-136, 139-157, 162-180, 206-225, 228-246, 249-267, 270-288, 293-312, 315-333, 336-354, 357-375, 378-396, 399-417, 420-438)

**Issue:** Nearly every tool repeats the identical pattern:

```python
try:
    config = device_manager.get_device(device)
    cmd = get_command(config.device_type, "<op>")
    with device_manager.connect(device) as conn:
        output = conn.send_command(cmd)
    audit.log_command(device, cmd, "<name>", True, len(output))
    return output
except Exception as e:
    audit.log_command(device, "", "<name>", False, error=str(e))
    return f"Error: {e}"
```

This is copy-pasted ~25 times with only the operation name and tool name changed,
making the module (1850+ lines) hard to maintain and prone to drift (e.g. a future fix
to error handling or audit logging must be applied in 25 places).

**Fix:** Extract a helper/decorator:

```python
def _run_show(operation: str, tool_name: str):
    def decorator(fn):
        @wraps(fn)
        def wrapper(device: str, **kwargs) -> str:
            try:
                config = device_manager.get_device(device)
                cmd = get_command(config.device_type, operation, **kwargs)
                with device_manager.connect(device) as conn:
                    output = conn.send_command(cmd)
                audit.log_command(device, cmd, tool_name, True, len(output))
                return output
            except Exception as e:
                audit.log_command(device, "", tool_name, False, error=str(e))
                return f"Error: {e}"
        return wrapper
    return decorator
```

### WR-04: `run_vendor_operation` silently sends an unformatted template when the operation needs parameters

**File:** `mcp/mcp-telecom/src/mcp_telecom/vendors/mappings.py:204-234`, `mcp/mcp-telecom/src/mcp_telecom/server.py:533-554`

**Issue:** `get_command()`'s last line is:

```python
return template.format(**kwargs) if kwargs else template
```

`run_vendor_operation(device, operation)` never passes any `kwargs`. If a caller invokes
`run_vendor_operation(device, "interface_detail")`, `get_command` takes the `else`
branch and returns the raw, unformatted template string (e.g.
`"show interface {interface}"` for Cisco) containing literal `{interface}` braces, which
then gets sent verbatim to the device and will fail or behave unpredictably. There is no
error surfaced to the caller indicating the operation requires a parameter that
`run_vendor_operation` cannot supply.

**Fix:** Have `get_command` detect unresolved `{...}` placeholders and raise a clear
`ValueError`, or have `run_vendor_operation` reject operations that are known to require
parameters:

```python
result = template if not kwargs else template.format(**kwargs)
if "{" in result and "}" in result:
    raise ValueError(f"Operation '{operation}' requires parameters not supplied")
return result
```

### WR-05: Broad `except Exception` blocks swallow errors without server-side logging

**File:** `mcp/mcp-telecom/src/mcp_telecom/server.py` (all tool functions, e.g. lines 70-72, 92-94, 113-115)

**Issue:** Every tool's `except Exception as e` branch only calls `audit.log_command(...)`
and returns `f"Error: {e}"` to the MCP client — there is no `logger.exception(...)` or
`logger.error(...)` call anywhere in these handlers. Real bugs (e.g. unexpected
`AttributeError`s from library internals) will be silently converted into an opaque
string returned to the caller with no stack trace captured server-side, making
production troubleshooting dependent entirely on the audit log's plain error string.

**Fix:** Add `logger.exception("Tool %s failed for %s", tool_name, device)` before
returning the error string in each handler (or centralize via the WR-03 decorator).

### WR-06: SNMP tools default to the insecure `"public"` community string over SNMPv2c

**File:** `mcp/mcp-telecom/src/mcp_telecom/server.py:1314-1424`

**Issue:** `snmp_get`, `snmp_walk`, and `snmp_device_overview` all default
`community: str = "public"`, the canonical well-known default. SNMPv2c community strings
are transmitted in cleartext with no authentication beyond the string itself. There is no
SNMPv3 option or warning in the tool docstrings about using a non-default community in
any environment beyond a lab.

**Fix:** Remove the `"public"` default (make `community` required), and/or add a
docstring warning plus SNMPv3 support path for production use.

## Info

### IN-01: Unused variable and no-op f-string in `openapi_to_mcp.py` CLI summary

**File:** `mcp/tooling/openapi_to_mcp.py:237, 239`

**Issue:** `total_ops = "unknown"` (line 237) is computed with a comment ("Would need to
parse the spec to count") but is never referenced in any of the subsequent `print(...)`
calls — dead code. Line 239, `print(f"Generated MCP server scaffold:")`, uses an
f-string with no interpolation.

**Fix:** Remove the unused `total_ops` assignment, or implement the spec-operation count
and use it; drop the superfluous `f` prefix on line 239.

### IN-02: Regex module imported inside a loop

**File:** `mcp/tooling/openapi_to_mcp.py:161-180` (specifically line 174)

**Issue:** `_build_route_maps_code` does `import re as _re` inside the `for op in
operations:` loop body, re-importing (cheap, but unnecessary) on every iteration.

**Fix:** Move `import re` to the top of the module alongside the other imports.

### IN-03: Dockerfile bakes the example device inventory and empty allowlist into the production image

**File:** `mcp/mcp-telecom/Dockerfile:25-27`

**Issue:** `COPY devices.yaml.example ./devices.yaml` and
`COPY command_allowlist.yaml ./command_allowlist.yaml` mean every built image ships with
the placeholder `router-lab-01.example.com` device entry and an empty allowlist baked
in by default, rather than requiring an explicit config mount. This is reasonable for a
Phase 2 scaffold but should be revisited before any image is used against production
devices, to avoid accidentally running against the placeholder config if a real
`devices.yaml` mount is forgotten.

**Fix:** Consider failing fast (or logging a prominent warning) at startup if
`MCP_TELECOM_DEVICES_FILE` was not explicitly overridden and only the baked-in example
is present.

### IN-04: `healthz` route appended to Starlette router without checking for conflicts

**File:** `mcp/mcp-telecom/src/mcp_telecom/server.py:1828-1841`

**Issue:** `app.router.routes.append(Route("/healthz", healthz))` appends directly to
the internal `routes` list rather than using a documented public API (the comment
acknowledges `StarletteWithLifespan` doesn't expose `.route()`), and there's no guard
against FastMCP's `http_app()` already defining a `/healthz`-prefixed MCP route in a
future FastMCP version, which could silently shadow this probe endpoint depending on
route ordering.

**Fix:** Add a comment/test asserting `/healthz` resolves to this handler (e.g. an
integration test hitting `/healthz` and asserting the `{"status": "ok"}` body), so a
future FastMCP upgrade that changes internal routing is caught.

---

_Reviewed: 2026-10-04T18:51:35Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
