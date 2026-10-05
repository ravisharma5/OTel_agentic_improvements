# Phase 4: SDG Pipeline and Dataset Production - Pattern Map

**Mapped:** 2026-10-05
**Updated:** 2026-10-05 (revision 3 -- fixed file classification for osft_validation, verify-langflow-mcp)
**Files analyzed:** 27 new/modified files
**Analogs found:** 22 / 27

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `sdg/scripts/run-generation.py` | utility | batch/transform | `scripts/check-config.py` | role-match |
| `sdg/scripts/run-evaluation.py` | utility | batch/transform | `scripts/check-config.py` | role-match |
| `sdg/scripts/serialize-osft.py` | utility | transform | `mcp/tooling/openapi_to_mcp.py` | partial |
| `sdg/lib/osft_validation.py` | library | transform | `mcp/tooling/allowlist_schema.py` | partial |
| `sdg/lib/test_osft_validation.py` | test | transform | `mcp/mcp-telecom/tests/test_safety.py` | role-match |
| `sdg/scripts/serve-gemma4.sh` | config/script | request-response | `scripts/verify-gateway.sh` | role-match |
| `sdg/scripts/start-agent.sh` | config/script | request-response | `scripts/verify-gateway.sh` | role-match |
| `sdg/scripts/verify-langflow-mcp.sh` | config/script | request-response | `scripts/verify-gateway.sh` | exact |
| `sdg/config/flow-training.yaml` | config | -- | `mcp/mcp-telecom/command_allowlist.yaml` | role-match |
| `sdg/config/flow-evaluation.yaml` | config | -- | `mcp/mcp-telecom/command_allowlist.yaml` | role-match |
| `sdg/config/seed-scenarios.yaml` | config | -- | `mcp/mcp-telecom/devices.yaml.example` | role-match |
| `sdg/config/model-config.yaml` | config | -- | `backends/openshift/configmap-backend-routing.yaml` | partial |
| `sdg/notebooks/01-dry-run.ipynb` | notebook | batch/transform | -- | no-analog |
| `sdg/notebooks/02-exploration.ipynb` | notebook | batch/transform | -- | no-analog |
| `sdg/notebooks/03-production-run.ipynb` | notebook | batch/transform | -- | no-analog |
| `sdg/scripts/test_serialize_osft.py` | test | transform | `mcp/mcp-telecom/tests/test_allowlist.py` | role-match |
| `mcp/mcp-telecom/src/mcp_telecom/safety.py` | middleware | request-response | self (modify in place) | exact |
| `mcp/mcp-telecom/src/mcp_telecom/tools/interfaces.py` | service | request-response | self (modify in place) | exact |
| `mcp/mcp-telecom/src/mcp_telecom/server.py` | controller | request-response | self (modify in place) | exact |
| `mcp/mcp-telecom/tests/test_allowlist.py` | test | unit | self (rewrite) + `tests/test_safety.py` | exact |
| `mcp/mcp-telecom/tests/test_interfaces.py` | test | unit | `mcp/mcp-telecom/tests/test_safety.py` | exact |
| `mcp/mcp-telecom/tests/test_compare_configs.py` | test | unit | `mcp/mcp-telecom/tests/test_safety.py` | exact |
| `mcp/mcp-telecom/command_allowlist.yaml` | config | -- | self (populate) | exact |
| `mcp/mcp-telecom/devices.yaml` | config | -- | `mcp/mcp-telecom/devices.yaml.example` | exact |
| `mcp/nwdaf/server.py` | controller | request-response | self (modify in place) | exact |
| `backends/specs/*.yaml` and `*.json` | config | -- | self (enrich in place) | exact |
| `backends/openshift/configmap-backend-routing.yaml` | config | -- | self (modify in place) | exact |
| `scripts/sync-backend-routing.sh` | utility | batch | `scripts/drift-check.sh` | exact |

## Pattern Assignments

### `mcp/mcp-telecom/src/mcp_telecom/safety.py` (middleware, modify -- CR-01)

**Analog:** self -- modify in place. Current file is the target.

**Current imports pattern** (lines 1-9):
```python
"""Command safety validation for MCP-Telecom."""
from __future__ import annotations
import re
```

**New imports to add** (per RESEARCH.md CR-01 fix):
```python
import os
from pathlib import Path
import yaml
```

**Current validate_command pattern** (lines 64-80):
```python
def validate_command(command: str) -> str | None:
    """Validate a command and return an error message if unsafe."""
    cmd = command.strip()
    if not cmd:
        return "Empty command"
    if not is_safe_command(cmd):
        return (
            f"Command blocked for safety: '{cmd}'. "
            f"Only read-only commands are allowed (show, display, ping, traceroute). "
            f"Configuration changes must be made through your standard change management process."
        )
    return None
```

**Extension point:** Add allowlist loading (file-cached, env-overridable path) and allowlist prefix check after the existing `is_safe_command()` call. The allowlist check is a NEW gate -- command must pass BOTH existing safety check AND allowlist prefix match.

---

### `mcp/mcp-telecom/src/mcp_telecom/tools/interfaces.py` (service, modify -- CR-02)

**Analog:** self -- modify in place.

**Current imports pattern** (lines 1-11):
```python
"""Interface monitoring tools for MCP-Telecom."""
from __future__ import annotations
from mcp_telecom.audit import AuditLogger
from mcp_telecom.connection import DeviceManager
from mcp_telecom.vendors.mappings import get_command
```

**Current show_interface_detail pattern** (lines 23-35):
```python
def show_interface_detail(
    device_manager: DeviceManager,
    audit: AuditLogger,
    device: str,
    interface: str,
) -> str:
    """Show detailed statistics for a specific interface."""
    config = device_manager.get_device(device)
    cmd = get_command(config.device_type, "interface_detail", interface=interface)
    with device_manager.connect(device) as conn:
        output = conn.send_command(cmd)
    audit.log_command(device, cmd, "show_interface_detail", True, len(output))
    return output
```

**Extension point:** Add `import re` at module level. Add regex constant `_INTERFACE_RE = re.compile(r"^[A-Za-z0-9_./:-]+$")`. Add regex validation of `interface` before `get_command()` call. Add `validate_command(cmd)` call after `get_command()` for defense-in-depth.

---

### `mcp/mcp-telecom/src/mcp_telecom/server.py` (controller, modify -- CR-03)

**Analog:** self -- modify in place.

**Current compare_configs pattern** (lines 461-500):
```python
@mcp.tool()
def compare_configs(device: str, backup_file: str) -> str:
    """Compare the current running config with a previous backup."""
    try:
        import difflib
        from pathlib import Path

        config = device_manager.get_device(device)
        cmd = get_command(config.device_type, "config_running")
        with device_manager.connect(device) as conn:
            current = conn.send_command(cmd, read_timeout=60)

        backup_path = Path(backup_file)
        if not backup_path.exists():
            return f"Error: Backup file not found: {backup_file}"

        previous = backup_path.read_text()
        # ... diff logic ...
    except Exception as e:
        audit.log_command(device, "", "compare_configs", False, error=str(e))
        return f"Error: {e}"
```

**Extension point:** Move `from pathlib import Path` to module level. Add `BACKUPS_DIR = Path("backups").resolve()`. Replace `backup_path = Path(backup_file)` with `candidate = (BACKUPS_DIR / Path(backup_file).name).resolve()` and add `is_relative_to(BACKUPS_DIR)` check.

---

### `mcp/nwdaf/server.py` (controller, modify -- D-15 h2c fix)

**Analog:** self -- modify in place.

**Current HTTP client pattern** (lines 114-115):
```python
# --- HTTP client (shared across all tools, single backend) ---
client = httpx2.AsyncClient(base_url=get_backend_url())
```

**Extension point:** Replace with conditional transport selection. When backend URL targets NextGCore (h2c), use `httpcore2.AsyncConnectionPool(http1=False, http2=True)` as the transport. When targeting Prism (HTTP/1.1), use default. Detection: add ConfigMap key or infer from port number.

**ConfigMap watcher pattern to preserve** (lines 51-112):
```python
BACKEND_ROUTING_PATH = os.environ.get(
    "BACKEND_ROUTING_FILE", "/config/backend-routing/NWDAF_BASE_URL"
)
_backend_url_lock = threading.Lock()
_backend_url = os.environ.get("NWDAF_BASE_URL", "http://localhost:4010")

def _load_backend_url():
    """Read backend URL from ConfigMap-mounted file and update state."""
    global _backend_url
    try:
        url = Path(BACKEND_ROUTING_PATH).read_text().strip()
        if url and (url.startswith("http://") or url.startswith("https://")):
            with _backend_url_lock:
                _backend_url = url
            client.base_url = url
            logger.info("Backend URL updated: %s", url)
        elif url:
            logger.warning("Invalid backend URL: %s", url)
    except FileNotFoundError:
        logger.debug("ConfigMap file not found at %s", BACKEND_ROUTING_PATH)
```

**Key requirement:** When `_load_backend_url()` fires on ConfigMap change, the transport must also be re-evaluated (h2c vs HTTP/1.1) and the client object recreated with the appropriate transport.

---

### `mcp/mcp-telecom/tests/test_allowlist.py` (test, rewrite -- CR-01)

**Analog:** Current self (structure to preserve) + `test_safety.py` (import pattern to follow).

**Current test_allowlist.py anti-pattern** (lines 19-43) -- tests a LOCAL reimplementation, not production code:
```python
def load_allowlist(allowlist_path: str | Path) -> list[str]:
    """Load the command allowlist from a YAML file."""
    # ... local copy of logic ...

def check_command_allowed(command: str, allowlist: list[str]) -> bool:
    """Check if a command is permitted by the allowlist."""
    # ... local copy of logic ...
```

**Target import pattern** -- from `test_safety.py` (lines 1-6):
```python
"""Tests for command safety validation."""
import pytest
from mcp_telecom.safety import is_safe_command, validate_command
```

**Rewrite:** Replace local `load_allowlist`/`check_command_allowed` functions with imports from `mcp_telecom.safety`. Test production `validate_command()` with allowlist enforcement. Keep the test class structure (parametrized, 3 classes: deny-by-default, accept-listed, reject-unlisted). Use `tmp_path` fixture + monkeypatch for `_ALLOWLIST_PATH` env var.

---

### `mcp/mcp-telecom/tests/test_interfaces.py` (test, new -- CR-02)

**Analog:** `mcp/mcp-telecom/tests/test_safety.py`

**Test structure pattern** (test_safety.py lines 1-9, 67-80):
```python
"""Tests for command safety validation."""
import pytest
from mcp_telecom.safety import is_safe_command, validate_command

class TestValidateCommand:
    def test_safe_command_returns_none(self):
        assert validate_command("show version") is None

    def test_dangerous_command_returns_error(self):
        result = validate_command("configure terminal")
        assert result is not None
        assert "blocked" in result.lower()
```

**Apply to test_interfaces.py:** Test that `show_interface_detail` rejects invalid interface names (containing `;`, `|`, `&&`, spaces, etc.) and accepts valid ones (e.g., `ge-0/0/0`, `eth1/1`, `Ethernet0/0/0/1`). Use parametrized test classes. Mock `device_manager` and `audit` using conftest.py's `device_manager` fixture pattern.

**Conftest fixture pattern** (conftest.py lines 1-41):
```python
"""Shared test fixtures for MCP-Telecom tests."""
import pytest
from mcp_telecom.connection import DeviceManager
from mcp_telecom.models import DeviceConfig, VendorType

@pytest.fixture
def device_manager():
    dm = DeviceManager()
    dm.add_device("test-nokia", DeviceConfig(
        device_type=VendorType.NOKIA_SROS,
        host="192.168.1.1",
        username="testuser", password="testpass",
    ))
    return dm
```

---

### `mcp/mcp-telecom/tests/test_compare_configs.py` (test, new -- CR-03)

**Analog:** `mcp/mcp-telecom/tests/test_safety.py`

**Apply same pattern as test_interfaces.py.** Test that `compare_configs` rejects path-traversal attempts (`../../etc/passwd`, `/etc/shadow`, `../../../secrets`) and accepts valid backup filenames (`backup-2024-01-01.cfg`). Use `tmp_path` fixture to create a temporary backups directory with test files.

---

### `sdg/scripts/run-generation.py` (utility, batch/transform)

**Analog:** `scripts/check-config.py`

**Script pattern** (check-config.py lines 1-19):
```python
#!/usr/bin/env python3
"""Check if virtualServers are in the gateway config secret."""
import json, base64, subprocess, sys

r = subprocess.run(
    ['oc', 'get', 'secret', 'mcp-gateway-config', '-n', 'otel25-gateway', '-o', 'json'],
    capture_output=True, text=True
)
d = json.loads(r.stdout)
# ... processing ...
```

**Conventions to follow:**
- Shebang line: `#!/usr/bin/env python3`
- Module docstring describing purpose
- Direct imports at top, no complex import structure
- Self-contained scripts that can run standalone

**SDG-specific pattern** (from RESEARCH.md Pattern 1):
```python
from sdg_hub import FlowRegistry, Flow

FlowRegistry.discover_flows()
flow = Flow.from_yaml(FlowRegistry.get_flow_path("MCP Server Distillation"))
flow.set_model_config(
    model="hosted_vllm/google/gemma-4-31B-it",
    api_key="<VLLM_API_KEY>",
    api_base="http://vllm-gemma4.rhoai-sdg.svc:8000/v1",
)
```

---

### `sdg/scripts/serialize-osft.py` (utility, transform)

**Analog:** `mcp/tooling/openapi_to_mcp.py` (closest Python transform script)

**Import + CLI pattern** (openapi_to_mcp.py lines 1-28):
```python
"""OpenAPI-to-MCP conversion CLI."""
from __future__ import annotations

import argparse
import sys
import textwrap
from datetime import datetime, timezone
from pathlib import Path
```

**Conventions to follow:**
- `from __future__ import annotations` at top
- `argparse` for CLI argument parsing
- `pathlib.Path` for file I/O
- Module-level docstring explaining usage

---

### `sdg/lib/osft_validation.py` (library, transform -- D-04)

**Analog:** `mcp/tooling/allowlist_schema.py` (closest schema-validation library)

**Key distinction:** This is a library module (no argparse, no CLI entry point), NOT a standalone script. Per amended D-04, it is imported by `sdg/scripts/run-evaluation.py` (Plan 07) and called automatically after the eval flow completes.

**Import pattern:**
```python
"""OSFT schema compliance validation library.

Per amended D-04, these functions are imported by run-evaluation.py
and called automatically after the eval flow completes.
"""
from __future__ import annotations
import json
from pathlib import Path
```

**Exports:** `validate_osft_line(line: dict) -> list[str]`, `validate_osft_file(path: str) -> tuple[bool, list[str]]`

---

### `sdg/lib/test_osft_validation.py` (test, new -- D-04)

**Analog:** `mcp/mcp-telecom/tests/test_safety.py`

**Apply same test structure pattern:** Class-based test grouping with parametrize. TestValidOSFT (valid cases), TestInvalidOSFT (missing fields, mismatched IDs, empty messages), TestFileValidation (file-level validation with tmp_path).

---

### `sdg/scripts/verify-langflow-mcp.sh` (shell script, new -- Open Question 3)

**Analog:** `scripts/verify-gateway.sh` (exact match -- same verification-script pattern with PASS/FAIL summary)

**Shell script header pattern** (verify-gateway.sh lines 1-22):
```bash
#!/usr/bin/env bash
# verify-langflow-mcp.sh -- Verify Langflow AgentBlock can consume MCP Gateway tools
#
# Resolves RESEARCH.md Open Question 3 and Assumption A4.
#
# Tests: gateway reachability, Langflow health, native MCP support, tool invocation
# Contingency: outputs adapter instructions if native MCP support absent
#
# Usage: sdg/scripts/verify-langflow-mcp.sh [gateway-url] [langflow-url]
#
# Requires: bash 4+, curl, jq

set -euo pipefail
```

**Conventions:** PASS/FAIL counter pattern, MCP_NATIVE detection flag, contingency section with adapter instructions, summary with exit codes. Follows verify-gateway.sh structure exactly.

---

### `sdg/scripts/test_serialize_osft.py` (test, new)

**Analog:** `mcp/mcp-telecom/tests/test_allowlist.py`

**Test pattern for data validation** (test_allowlist.py lines 46-72):
```python
class TestAllowlistDenyByDefault:
    """Test that an empty allowlist rejects all commands."""

    def test_empty_allowlist_rejects_show_command(self):
        allowlist: list[str] = []
        assert check_command_allowed("show bgp summary", allowlist) is False

class TestAllowlistYAMLLoading:
    """Test YAML file loading for the allowlist."""

    def test_load_populated_allowlist_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump({"allowed_commands": commands}, f)
            f.flush()
            allowlist = load_allowlist(f.name)
        os.unlink(f.name)
        assert allowlist == commands
```

**Apply pattern:** Use class-based test grouping. Test valid OSFT JSONL output (correct roles, tool_call_id threading, required fields). Test invalid cases (missing tool_call_id, empty messages, malformed tool_calls). Use `tmp_path` for file I/O tests.

---

### `sdg/scripts/serve-gemma4.sh` and `sdg/scripts/start-agent.sh` (shell scripts)

**Analog:** `scripts/verify-gateway.sh`

**Shell script header pattern** (verify-gateway.sh lines 1-22):
```bash
#!/usr/bin/env bash
# verify-gateway.sh -- RHCL MCP Gateway end-to-end verification
#
# Modes:
#   initialize:  MCP initialize handshake
#   tools-list:  List all tools via gateway
#
# Usage: scripts/verify-gateway.sh <mode> [gateway-url] [jwt-token]
#
# Requires: bash 4+, curl, jq

set -euo pipefail
```

**Configuration pattern** (verify-gateway.sh lines 24-28):
```bash
# --- Configuration ---
MODE="${1:-}"
GATEWAY_URL="${2:-http://mcp.apps.cluster-domain/mcp}"
JWT_TOKEN="${3:-}"
```

**Conventions to follow:**
- `set -euo pipefail` safety
- Environment variable defaults with `${VAR:-default}`
- Usage message with argument descriptions
- Descriptive comment block at file top

---

### `scripts/sync-backend-routing.sh` (utility, batch)

**Analog:** `scripts/drift-check.sh` (exact match -- both read cluster state and compare/sync ConfigMaps)

**Auth + oc pattern** (drift-check.sh lines 4-15):
```bash
set -euo pipefail

GATEWAY_HOST=$(oc get route mcp-gateway -n otel25-gateway -o jsonpath='{.spec.host}' 2>/dev/null)
# ...
CLIENT_SECRET=$(oc get secret keycloak-client-secret-mcp-gateway -n otel25-gateway \
    -o jsonpath='{.data.CLIENT_SECRET}' | base64 -d)

if [ -z "$GATEWAY_HOST" ] || [ -z "$CLIENT_SECRET" ]; then
  echo "ERROR: Could not resolve ... (is oc authenticated?)"
  exit 1
fi
```

**ConfigMap read pattern** (from drift-check.sh, adapted):
```bash
# Read canonical ConfigMap from otel25-backends
CANONICAL=$(oc get configmap backend-routing -n otel25-backends -o json 2>/dev/null)
if [ -z "$CANONICAL" ]; then
  echo "ERROR: Could not read canonical ConfigMap in otel25-backends"
  exit 1
fi
```

**Sync action pattern:** Use `oc patch configmap backend-routing -n otel25-mcp --type merge -p '...'` to sync data from otel25-backends copy to otel25-mcp copy. Report PASS/FAIL summary like verify-gateway.sh.

**Summary pattern** (verify-gateway.sh lines 466-484):
```bash
TOTAL=$((PASS + FAIL))
echo "=== Results: sync ==="
echo "Passed: $PASS"
echo "Failed: $FAIL"
echo ""
if [[ $FAIL -eq 0 && $PASS -gt 0 ]]; then
  echo "OVERALL: PASS"
  exit 0
else
  echo "OVERALL: FAIL"
  exit 1
fi
```

---

### `sdg/config/*.yaml` (config files)

**Analog:** `mcp/mcp-telecom/command_allowlist.yaml` and `mcp/mcp-telecom/devices.yaml.example`

**Config file header comment pattern** (command_allowlist.yaml lines 1-28):
```yaml
# MCP-Telecom Command Allowlist
# ==============================
#
# DENY-BY-DEFAULT SAFETY MECHANISM
# ---------------------------------
# When the `allowed_commands` list is empty, ALL CLI commands submitted
# through the safe-exec tool (run_command) are rejected.
#
# Phase 4 populates this with specific permitted commands when wiring
# real network devices.
#
# FORMAT:
# Each entry is a command prefix that will be allowed.
#
# Example populated allowlist (for Phase 4):
#   allowed_commands:
#     - "show bgp summary"
```

**Conventions to follow:**
- Block comment header with title and separator line
- Section headings in CAPS
- Inline example values showing expected format
- Document purpose, format, and example usage

---

### `backends/specs/*.yaml` and `*.json` (spec enrichment -- D-16)

**Analog:** Self -- enrich in place.

**TMF642 existing example pattern** (tmf642_alarm_v5.0.1.oas.yaml, around lines 3201-3570):
Spec already has response-level `example:` blocks (e.g., `Alarm_list_example`, `Alarm_retrieve_example`). But schema-level properties under `components/schemas/` lack per-property `example:` values, which is what Prism's dynamic mock generator uses.

**Enrichment target pattern** -- add `example:` to schema properties:
```yaml
# BEFORE (current -- Prism generates "Lorem ipsum" for these):
AlarmType:
  type: string
  description: The type of the alarm

# AFTER (enriched -- Prism generates realistic values):
AlarmType:
  type: string
  description: The type of the alarm
  example: "environmentalAlarm"
```

**TMF628 priority:** Only 3 `example` mentions in 5,318 lines. This is the highest-priority enrichment target.

---

### `backends/openshift/configmap-backend-routing.yaml` (config, modify -- D-17)

**Analog:** self -- modify in place.

**Current pattern** (full file, lines 39-61):
```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: backend-routing
  namespace: otel25-backends
  labels:
    purpose: backend-routing
    phase: "1"
data:
  TMF642_BASE_URL: "http://prism-tmf642.otel25-backends.svc.cluster.local:4010"
  TMF628_BASE_URL: "http://prism-tmf628.otel25-backends.svc.cluster.local:4010"
  TMF621_BASE_URL: "http://prism-tmf621.otel25-backends.svc.cluster.local:4010"
  CAMARA_BASE_URL: "http://prism-camara.otel25-backends.svc.cluster.local:4010"
  CAMARA_RETRIEVAL_BASE_URL: "http://prism-camara-retrieval.otel25-backends.svc.cluster.local:4010"
  NWDAF_BASE_URL: "http://nextgcore-nwdaf.otel25-backends.svc.cluster.local:7777"
```

**Extension points:**
1. Add `NWDAF_EVENTS_BASE_URL` for the EventsSubscription path divergence (D-15).
2. Add `NWDAF_PROTOCOL` key (`h2c` or `http1.1`) for transport selection.
3. Add device backend entries if Containerlab devices need routing through this ConfigMap.
4. Update `phase` label from `"1"` to `"4"`.

---

### `mcp/mcp-telecom/devices.yaml` (config, new from template -- D-14)

**Analog:** `mcp/mcp-telecom/devices.yaml.example`

**Template pattern** (devices.yaml.example lines 30-53):
```yaml
devices:
  # Example device entry -- replace with real device details in Phase 4
  - hostname: "router-lab-01.example.com"
    platform: "cisco_ios"
    device_type: "router"
    port: 22
    timeout: 30
    credential_secret_ref: "mcp-telecom-device-creds"
```

**Population:** Replace example entries with Containerlab-assigned device targets. Use `ContainerlabManager.generate_devices_yaml()` output as the source (see `containerlab.py` lines 1-50 for the generator). Management IPs come from Containerlab's `172.20.20.0/24` default subnet.

---

## Shared Patterns

### Shell Script Structure
**Source:** `scripts/verify-gateway.sh` (lines 1-22, 466-484)
**Apply to:** `sdg/scripts/serve-gemma4.sh`, `sdg/scripts/start-agent.sh`, `sdg/scripts/verify-langflow-mcp.sh`, `scripts/sync-backend-routing.sh`
```bash
#!/usr/bin/env bash
# <script-name>.sh -- <one-line description>
#
# <detailed description with modes/usage>
#
# Usage: scripts/<script-name>.sh <args>
# Requires: <dependencies>

set -euo pipefail

# --- Configuration ---
VAR="${1:-default}"

# ... main logic ...

# --- Summary ---
echo "=== Results ==="
# PASS/FAIL exit codes
```

### Python Test Structure
**Source:** `mcp/mcp-telecom/tests/test_safety.py` (lines 1-80)
**Apply to:** All new test files (`test_interfaces.py`, `test_compare_configs.py`, `test_serialize_osft.py`, `sdg/lib/test_osft_validation.py`, rewritten `test_allowlist.py`)
```python
"""Tests for <module description>."""
import pytest
from <module> import <function_under_test>

class Test<Feature>:
    """Test <feature description>."""

    @pytest.mark.parametrize("input", [...])
    def test_<valid_cases>(self, input):
        assert <function>(input) is <expected>

    @pytest.mark.parametrize("input", [...])
    def test_<invalid_cases>(self, input):
        result = <function>(input)
        assert result is not None
        assert "<error keyword>" in result.lower()
```

### Python Script Convention
**Source:** `scripts/check-config.py` (lines 1-3) + `mcp/tooling/openapi_to_mcp.py` (lines 1-28)
**Apply to:** `sdg/scripts/run-generation.py`, `sdg/scripts/run-evaluation.py`, `sdg/scripts/serialize-osft.py`
```python
#!/usr/bin/env python3
"""<One-line description of what the script does.>

<Detailed description and usage instructions.>
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
```

### Python Library Module Convention (no CLI)
**Source:** `mcp/tooling/allowlist_schema.py`
**Apply to:** `sdg/lib/osft_validation.py`
```python
"""<One-line description of library purpose.>

<Per D-04: imported by run-evaluation.py, not a standalone script.>
"""
from __future__ import annotations
import json
from pathlib import Path

# NO argparse, NO if __name__ == "__main__"
```

### MCP Server Modification Pattern (ConfigMap watcher)
**Source:** `mcp/nwdaf/server.py` (lines 51-115)
**Apply to:** Any modification to `nwdaf/server.py` must preserve the ConfigMap file-watcher, lock-based URL access, and health endpoint patterns.
```python
BACKEND_ROUTING_PATH = os.environ.get(
    "BACKEND_ROUTING_FILE", "/config/backend-routing/NWDAF_BASE_URL"
)
_backend_url_lock = threading.Lock()
_backend_url = os.environ.get("NWDAF_BASE_URL", "http://localhost:4010")

def _load_backend_url():
    global _backend_url
    try:
        url = Path(BACKEND_ROUTING_PATH).read_text().strip()
        if url and (url.startswith("http://") or url.startswith("https://")):
            with _backend_url_lock:
                _backend_url = url
            client.base_url = url
    except FileNotFoundError:
        logger.debug("ConfigMap file not found")
```

### MCP-Telecom Tool Function Pattern
**Source:** `mcp/mcp-telecom/src/mcp_telecom/tools/interfaces.py` (lines 13-35)
**Apply to:** Modifications to `interfaces.py` (CR-02 fix) must preserve this structure.
```python
def show_interface_detail(
    device_manager: DeviceManager,
    audit: AuditLogger,
    device: str,
    interface: str,
) -> str:
    """Show detailed statistics for a specific interface."""
    # NEW: validation here (CR-02)
    config = device_manager.get_device(device)
    cmd = get_command(config.device_type, "interface_detail", interface=interface)
    # NEW: validate_command(cmd) here (defense-in-depth)
    with device_manager.connect(device) as conn:
        output = conn.send_command(cmd)
    audit.log_command(device, cmd, "show_interface_detail", True, len(output))
    return output
```

### YAML Config File Convention
**Source:** `mcp/mcp-telecom/command_allowlist.yaml` (lines 1-29)
**Apply to:** `sdg/config/flow-training.yaml`, `sdg/config/flow-evaluation.yaml`, `sdg/config/seed-scenarios.yaml`, `sdg/config/model-config.yaml`
```yaml
# <Config File Name>
# ==================
#
# <PURPOSE HEADING>
# -----------------
# <Description of what this config controls>
#
# FORMAT:
# <Description of expected format>
#
# Example:
#   <example values>

<key>: <value>
```

### Cluster Auth Pattern (for cross-cluster scripts)
**Source:** `scripts/drift-check.sh` (lines 6-21)
**Apply to:** `scripts/sync-backend-routing.sh`, and any script that needs Keycloak JWT
```bash
GATEWAY_HOST=$(oc get route mcp-gateway -n otel25-gateway -o jsonpath='{.spec.host}' 2>/dev/null)
CLIENT_SECRET=$(oc get secret keycloak-client-secret-mcp-gateway -n otel25-gateway \
    -o jsonpath='{.data.CLIENT_SECRET}' | base64 -d)

TOKEN=$(curl -sk -X POST "${KEYCLOAK_URL}/realms/mcp/protocol/openid-connect/token" \
  -d "grant_type=password&client_id=mcp-gateway&client_secret=${CLIENT_SECRET}&..." \
  | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))")
```

### Pytest Configuration
**Source:** `mcp/mcp-telecom/pyproject.toml` (lines 79-81)
**Apply to:** Any new test directories
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
asyncio_mode = "auto"
```

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `sdg/notebooks/01-dry-run.ipynb` | notebook | batch/transform | No Jupyter notebooks exist in the codebase. Use RESEARCH.md Pattern 1 (sdg_hub flow configuration) as the code pattern source. |
| `sdg/notebooks/02-exploration.ipynb` | notebook | batch/transform | No Jupyter notebooks exist in the codebase. Use RESEARCH.md Pattern 1 for the sdg_hub API calls. |
| `sdg/notebooks/03-production-run.ipynb` | notebook | batch/transform | No Jupyter notebooks exist in the codebase. Use RESEARCH.md Pattern 1 with production-scale runtime_params. |
| `sdg/README.md` | documentation | -- | Documentation file -- no analog needed, follow standard README conventions for recipe docs. |

**Notebook guidance:** Since no notebooks exist in the codebase, follow these conventions derived from the Python script patterns:
- Each notebook should start with a markdown cell containing the equivalent of the script docstring (purpose, prerequisites, usage)
- Code cells should follow the same import conventions as `scripts/check-config.py` and `mcp/tooling/openapi_to_mcp.py`
- Use the sdg_hub API patterns from RESEARCH.md Pattern 1 directly
- Include validation cells that verify output (print counts, sample rows, schema checks)

## Metadata

**Analog search scope:** `scripts/`, `mcp/mcp-telecom/src/`, `mcp/mcp-telecom/tests/`, `mcp/nwdaf/`, `mcp/tooling/`, `backends/specs/`, `backends/openshift/`, `gateway/openshift/`
**Files scanned:** 45+ files across 8 directories
**Pattern extraction date:** 2026-10-05
