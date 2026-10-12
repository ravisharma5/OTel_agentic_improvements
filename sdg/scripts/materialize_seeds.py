#!/usr/bin/env python3
"""Materialize MCP Gateway tool schemas into a structured seed dataset.

Queries the MCP Gateway's tools/list endpoint (performing the required
initialize handshake first to acquire Mcp-Session-Id), extracts per-tool
metadata (name, description, inputSchema), cross-references with
seed-scenarios.yaml curriculum tiers, and produces a seed dataset JSONL
file that sdg_hub's mcp_distillation_training flow can consume as input.

Usage (standalone CLI):
    python3 sdg/scripts/materialize_seeds.py \\
        --gateway-url https://mcp.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com/mcp \\
        --keycloak-url https://mcp-keycloak-otel25-gateway.apps.cluster-wfhjs... \\
        --client-id sdg-pipeline

Usage (importable):
    from sdg.scripts.materialize_seeds import materialize_tool_seeds
    count = materialize_tool_seeds(tools, "sdg/config/seed-scenarios.yaml", "output.jsonl")

References:
    D-02:  mcp_distillation_training flow expects structured seed input
    D-12:  MCP Gateway tools available via tools/list
    SDG-02: Curriculum ordering (single-tool to closed-loop)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    # Fallback: attempt httpx if requests not installed
    requests = None
    try:
        import httpx as _httpx_fallback
    except ImportError:
        _httpx_fallback = None

try:
    import yaml
except ImportError:
    yaml = None


# ─── HTTP Helpers ────────────────────────────────────────────────────────────


def _http_post(url: str, headers: dict, json_body: dict, timeout: int = 30) -> tuple:
    """POST JSON and return (status_code, response_headers, response_json).

    Supports both requests and httpx as HTTP backends.
    """
    if requests is not None:
        resp = requests.post(url, headers=headers, json=json_body, timeout=timeout, verify=False)
        return resp.status_code, dict(resp.headers), resp.json()
    elif _httpx_fallback is not None:
        resp = _httpx_fallback.post(url, headers=headers, json=json_body, timeout=timeout, verify=False)
        return resp.status_code, dict(resp.headers), resp.json()
    else:
        raise ImportError("Neither 'requests' nor 'httpx' is installed. Install one: pip install requests")


# ─── JWT Acquisition ─────────────────────────────────────────────────────────


def acquire_jwt(keycloak_url: str, client_id: str, client_secret: str) -> str:
    """Acquire a JWT token from Keycloak using client_credentials grant.

    Args:
        keycloak_url: Base URL of the Keycloak instance.
        client_id: Client ID registered in the mcp realm.
        client_secret: Client secret for authentication.

    Returns:
        JWT access token string.

    Raises:
        RuntimeError: If token acquisition fails.
    """
    token_endpoint = f"{keycloak_url}/realms/mcp/protocol/openid-connect/token"
    data = {
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }

    if requests is not None:
        resp = requests.post(token_endpoint, data=data, timeout=30, verify=False)
        if resp.status_code != 200:
            raise RuntimeError(f"Keycloak returned HTTP {resp.status_code}: {resp.text}")
        token = resp.json().get("access_token")
    elif _httpx_fallback is not None:
        resp = _httpx_fallback.post(token_endpoint, data=data, timeout=30, verify=False)
        if resp.status_code != 200:
            raise RuntimeError(f"Keycloak returned HTTP {resp.status_code}: {resp.text}")
        token = resp.json().get("access_token")
    else:
        raise ImportError("Neither 'requests' nor 'httpx' is installed.")

    if not token:
        raise RuntimeError("Token response missing 'access_token' field")

    return token


# ─── MCP Session Handshake ───────────────────────────────────────────────────


def mcp_initialize(gateway_url: str, jwt: str) -> str:
    """Perform the MCP initialize handshake and return the Mcp-Session-Id.

    Sends a JSON-RPC initialize request to the MCP Gateway, which returns
    the session ID in the Mcp-Session-Id response header. This session ID
    MUST be included on all subsequent requests to the gateway.

    Args:
        gateway_url: MCP Gateway endpoint URL.
        jwt: JWT access token for Authorization header.

    Returns:
        Mcp-Session-Id string from the response headers.

    Raises:
        RuntimeError: If the handshake fails or no session ID is returned.
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {jwt}",
    }
    body = {
        "jsonrpc": "2.0",
        "method": "initialize",
        "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "sdg-pipeline", "version": "1.0"},
        },
        "id": 1,
    }

    status, resp_headers, resp_json = _http_post(gateway_url, headers, body)

    if status != 200:
        raise RuntimeError(f"MCP initialize failed with HTTP {status}")

    if "result" not in resp_json:
        raise RuntimeError(f"MCP initialize response missing 'result': {resp_json}")

    # Extract Mcp-Session-Id (case-insensitive header lookup)
    session_id = None
    for key, value in resp_headers.items():
        if key.lower() == "mcp-session-id":
            session_id = value
            break

    if not session_id:
        raise RuntimeError("MCP initialize response missing Mcp-Session-Id header")

    return session_id


# ─── Fetch Tool Schemas ─────────────────────────────────────────────────────


def fetch_tools(gateway_url: str, jwt: str, session_id: str) -> list[dict]:
    """Fetch tool schemas from the MCP Gateway via tools/list.

    Args:
        gateway_url: MCP Gateway endpoint URL.
        jwt: JWT access token for Authorization header.
        session_id: Mcp-Session-Id from the initialize handshake.

    Returns:
        List of tool dicts, each with 'name', 'description', 'inputSchema'.

    Raises:
        RuntimeError: If the tools/list call fails.
    """
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "Authorization": f"Bearer {jwt}",
        "Mcp-Session-Id": session_id,
    }
    body = {
        "jsonrpc": "2.0",
        "method": "tools/list",
        "id": 2,
    }

    status, _, resp_json = _http_post(gateway_url, headers, body)

    if status != 200:
        raise RuntimeError(f"tools/list failed with HTTP {status}")

    result = resp_json.get("result", {})
    tools = result.get("tools", [])

    if not tools:
        raise RuntimeError("tools/list returned 0 tools -- check gateway configuration")

    return tools


# ─── Seed Materialization ───────────────────────────────────────────────────


def materialize_tool_seeds(
    tools: list[dict],
    seed_scenarios_path: str | Path,
    output_path: str | Path,
) -> int:
    """Cross-reference MCP tools with curriculum tiers and produce seed JSONL.

    Each seed-scenarios.yaml scenario becomes one row matching sdg_hub's real
    "MCP Server Distillation" flow input contract -- required_columns=
    ['tool_list', 'mcp_server_name', 'mcp_server_description'] (verified
    against the installed sdg_hub==0.9.4 package's
    Flow.get_dataset_requirements(), not the flow's own docs, which don't
    cover this). tool_list is the scenario's tool_subset resolved to full
    tool objects -- this is what actually scopes which tools the flow's
    SamplerBlock can draw into a generated question, which is why keeping
    each scenario's hand-curated tool_subset (not the full 80-tool gateway
    inventory) is what keeps generation grounded to a coherent workflow
    instead of arbitrary cross-domain tool combinations.

    mcp_server_description carries the scenario's own description as
    grounding context for the flow's exploration/question-generation
    prompts -- the flow does NOT use it as literal question text, it
    generates its own questions from tool_list + this description.

    Extra passthrough columns (tier, complexity, scenario_name,
    intended_tools) aren't part of sdg_hub's required/optional schema, but
    survive RowMultiplierBlock/SamplerBlock (they only touch the columns
    they're configured to read) and are what tool_coverage_report.py uses
    to compare intended vs. actually-called tools per scenario later.

    Args:
        tools: List of tool dicts from fetch_tools() (name, description, inputSchema).
        seed_scenarios_path: Path to seed-scenarios.yaml.
        output_path: Path for output JSONL file.

    Returns:
        Number of seed records written.

    Raises:
        ValueError: If any scenario references a tool_subset name not found
            in the live gateway's tools/list response -- a silent mismatch
            here (e.g. a stale naming-convention assumption) was the actual
            root cause of a 100% seed-resolution failure found in practice;
            fail loudly instead of emitting a placeholder record.
    """
    if yaml is None:
        raise ImportError("PyYAML is required: pip install pyyaml")

    seed_scenarios_path = Path(seed_scenarios_path)
    output_path = Path(output_path)

    # Load seed scenarios
    with open(seed_scenarios_path) as f:
        scenarios_config = yaml.safe_load(f)

    tiers = scenarios_config.get("tiers", {})

    # Build tool lookup by name
    tool_map = {}
    for tool in tools:
        name = tool.get("name", "")
        tool_map[name] = {
            "name": name,
            "description": tool.get("description", ""),
            "inputSchema": tool.get("inputSchema", {}),
        }

    # Ensure output directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    records_written = 0
    unresolved: list[str] = []

    with open(output_path, "w") as out:
        for tier_name, tier_config in tiers.items():
            complexity = tier_config.get("complexity", 0)
            scenarios = tier_config.get("scenarios", [])

            for scenario in scenarios:
                scenario_name = scenario.get("name") or f"{tier_name}_unnamed_{records_written}"
                tool_subset = scenario.get("tool_subset", [])
                scenario_desc = scenario.get("description", "")

                # Resolve tool metadata for each tool in the subset against
                # the live gateway -- fail loudly on any miss (see docstring).
                resolved_tools = []
                for tool_name in tool_subset:
                    if tool_name not in tool_map:
                        unresolved.append(f"{scenario_name}: {tool_name}")
                        continue
                    resolved_tools.append(tool_map[tool_name])

                record = {
                    "mcp_server_name": scenario_name,
                    "mcp_server_description": (
                        f"Telecom NOC fault-prediction tool collection for: {scenario_desc}"
                    ),
                    "tool_list": resolved_tools,
                    # Passthrough tracking columns -- not part of sdg_hub's
                    # schema, consumed by tool_coverage_report.py.
                    "tier": tier_name,
                    "complexity": complexity,
                    "scenario_name": scenario_name,
                    "intended_tools": tool_subset,
                }

                out.write(json.dumps(record) + "\n")
                records_written += 1

    if unresolved:
        raise ValueError(
            "The following scenario tool_subset entries were not found in the "
            "live gateway's tools/list response (naming mismatch?): "
            + "; ".join(unresolved)
        )

    return records_written


# ─── CLI Entry Point ─────────────────────────────────────────────────────────


def main() -> int:
    """CLI entry point for seed materialization."""
    parser = argparse.ArgumentParser(
        description="Materialize MCP Gateway tool schemas into sdg_hub seed dataset.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Materialize from live gateway
  python3 sdg/scripts/materialize_seeds.py \\
      --gateway-url https://mcp.apps.cluster-wfhjs.../mcp \\
      --keycloak-url https://mcp-keycloak-otel25-gateway.apps.cluster-wfhjs...

  # Custom output path
  python3 sdg/scripts/materialize_seeds.py \\
      --output sdg/data/seeds/custom_seeds.jsonl
        """,
    )
    parser.add_argument(
        "--gateway-url",
        default=os.environ.get(
            "GATEWAY_URL",
            "https://mcp.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com/mcp",
        ),
        help="MCP Gateway endpoint URL",
    )
    parser.add_argument(
        "--keycloak-url",
        default=os.environ.get(
            "KEYCLOAK_URL",
            "https://mcp-keycloak-otel25-gateway.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com",
        ),
        help="Keycloak base URL",
    )
    parser.add_argument(
        "--client-id",
        default=os.environ.get("CLIENT_ID", "sdg-pipeline"),
        help="Keycloak client ID (default: sdg-pipeline)",
    )
    parser.add_argument(
        "--client-secret",
        default=os.environ.get("CLIENT_SECRET", ""),
        help="Keycloak client secret (default: from CLIENT_SECRET env var)",
    )
    parser.add_argument(
        "--seeds-config",
        default="sdg/config/seed-scenarios.yaml",
        help="Path to seed-scenarios.yaml (default: sdg/config/seed-scenarios.yaml)",
    )
    parser.add_argument(
        "--output",
        default="sdg/data/seeds/tool_metadata.jsonl",
        help="Output JSONL path (default: sdg/data/seeds/tool_metadata.jsonl)",
    )

    args = parser.parse_args()

    if not args.client_secret:
        print("ERROR: --client-secret or CLIENT_SECRET env var is required.", file=sys.stderr)
        return 1

    print("=== MCP Tool Schema Seed Materialization ===")
    print(f"Gateway:      {args.gateway_url}")
    print(f"Keycloak:     {args.keycloak_url}")
    print(f"Client ID:    {args.client_id}")
    print(f"Seeds config: {args.seeds_config}")
    print(f"Output:       {args.output}")
    print()

    # Step 1: Acquire JWT
    print("--- Step 1: Acquiring JWT token ---")
    jwt = acquire_jwt(args.keycloak_url, args.client_id, args.client_secret)
    print(f"  JWT acquired ({len(jwt)} chars)")

    # Step 2: MCP initialize handshake
    print("--- Step 2: MCP initialize handshake ---")
    session_id = mcp_initialize(args.gateway_url, jwt)
    print(f"  Mcp-Session-Id: {session_id[:16]}...")

    # Step 3: Fetch tools
    print("--- Step 3: Fetching tool schemas ---")
    tools = fetch_tools(args.gateway_url, jwt, session_id)
    print(f"  {len(tools)} tools discovered")

    # Step 4: Materialize seeds
    print("--- Step 4: Materializing seed dataset ---")
    count = materialize_tool_seeds(tools, args.seeds_config, args.output)
    print(f"  {count} seed records produced")

    # Summary
    print()
    print("=== Summary ===")
    print(f"Tools discovered:    {len(tools)}")
    print(f"Seed records:        {count}")

    # Count per tier
    if yaml is not None:
        with open(args.seeds_config) as f:
            tiers = yaml.safe_load(f).get("tiers", {})
        tier_count = len(tiers)
        print(f"Curriculum tiers:    {tier_count}")
        for tier_name in tiers:
            scenarios = tiers[tier_name].get("scenarios", [])
            print(f"  {tier_name}: {len(scenarios)} scenarios")

    print(f"Output written to:   {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
