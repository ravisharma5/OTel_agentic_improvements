"""Tests proving that allowlist filtering works end-to-end.

Uses a synthetic 2-operation OpenAPI spec (POST /alpha, GET /beta) with
an allowlist that includes only POST /alpha. Verifies:
  1. Static source-text: generated scaffold contains RouteMap for /alpha
     but NOT for /beta, plus catch-all EXCLUDE.
  2. Dynamic runtime: generated scaffold starts as a server and tools/list
     returns exactly 1 tool corresponding to /alpha, not /beta.

This test exists because the real CAMARA spec has only 1 operation, so a
broken filter would still pass the CAMARA smoke test (addresses Cursor
HIGH review finding).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx
import pytest

# Paths relative to tests/ directory
TESTS_DIR = Path(__file__).parent
TOOLING_DIR = TESTS_DIR.parent
SYNTHETIC_SPEC = TESTS_DIR / "synthetic_two_op_spec.yaml"
SYNTHETIC_ALLOWLIST = TESTS_DIR / "synthetic_allowlist.yaml"


def _parse_sse_json(response_text: str) -> dict:
    """Extract JSON-RPC response from SSE-formatted response body.

    FastMCP's Streamable HTTP returns SSE format:
        event: message
        data: {"jsonrpc": "2.0", ...}

    This function extracts and parses the JSON from the 'data:' line.
    """
    for line in response_text.strip().splitlines():
        if line.startswith("data: "):
            return json.loads(line[len("data: "):])
    raise ValueError(f"No 'data:' line found in SSE response: {response_text}")


def _generate_scaffold(output_path: str) -> str:
    """Run the conversion CLI and return the generated scaffold source."""
    result = subprocess.run(
        [
            sys.executable,
            str(TOOLING_DIR / "openapi_to_mcp.py"),
            "--spec", str(SYNTHETIC_SPEC),
            "--allowlist", str(SYNTHETIC_ALLOWLIST),
            "--output", output_path,
        ],
        capture_output=True,
        text=True,
        cwd=str(TOOLING_DIR),
    )
    assert result.returncode == 0, f"CLI failed: {result.stderr}"
    return Path(output_path).read_text()


def test_allowlist_excludes_non_allowlisted_operation():
    """Prove operation filtering works via static and dynamic checks.

    Static: generated code has RouteMap pattern for /alpha, catch-all EXCLUDE,
    and does NOT have RouteMap for /beta.

    Dynamic: start the generated server (stateless HTTP mode), POST
    tools/list, assert exactly 1 tool matching /alpha.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        scaffold_path = os.path.join(tmpdir, "test_server.py")

        # Generate the scaffold
        source = _generate_scaffold(scaffold_path)

        # --- Static source-text assertions ---

        # (a) Generated code contains RouteMap pattern for /alpha (allowlisted)
        assert '/alpha' in source and 'pattern=' in source, (
            "Generated scaffold missing RouteMap pattern for /alpha"
        )

        # (b) Generated code contains catch-all EXCLUDE
        assert "RouteMap(mcp_type=MCPType.EXCLUDE)" in source, (
            "Generated scaffold missing catch-all EXCLUDE RouteMap"
        )

        # (c) Generated code does NOT contain RouteMap pattern for /beta (excluded)
        assert '/beta' not in source, (
            "Generated scaffold should NOT contain RouteMap for /beta"
        )

        # --- Dynamic runtime assertion ---
        # Start the generated scaffold as a subprocess, query tools/list,
        # assert exactly 1 tool for /alpha.

        proc = subprocess.Popen(
            [sys.executable, scaffold_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=tmpdir,
        )

        try:
            # Wait for server startup (retry tools/list up to 10 seconds)
            # The generated scaffold runs in stateless_http mode, so
            # tools/list works without prior initialize.
            server_url = "http://localhost:8000/mcp"
            tools_resp = None
            deadline = time.monotonic() + 10.0

            while time.monotonic() < deadline:
                try:
                    resp = httpx.post(
                        server_url,
                        json={"jsonrpc": "2.0", "method": "tools/list", "id": 1},
                        timeout=2.0,
                    )
                    if resp.status_code == 200:
                        tools_resp = resp
                        break
                except (httpx.ConnectError, httpx.ReadError):
                    pass
                time.sleep(0.5)

            assert tools_resp is not None, (
                f"Server failed to start within 10s. "
                f"stderr: {proc.stderr.read().decode() if proc.stderr else 'N/A'}"
            )

            # Parse SSE-formatted response
            data = _parse_sse_json(tools_resp.text)
            assert "result" in data, f"No result in response: {data}"

            tools = data["result"].get("tools", [])
            tool_names = [t["name"] for t in tools]

            # Assert exactly 1 tool (from /alpha, not /beta)
            assert len(tools) == 1, (
                f"Expected exactly 1 tool, got {len(tools)}: {tool_names}"
            )

            # The tool name should correspond to /alpha operation
            # FastMCP from_openapi() generates tool names from operationId
            # or path+method. The synthetic spec has operationId "createAlpha".
            tool_name = tool_names[0]
            assert "alpha" in tool_name.lower() or "create" in tool_name.lower(), (
                f"Expected tool for /alpha operation, got: {tool_name}"
            )

        finally:
            # Kill the subprocess
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait()
