#!/usr/bin/env python3
"""refresh-mcp-token.py -- Re-mint the Keycloak JWT and push it into Langflow's
registered MCP server config.

The `sdg-pipeline` Keycloak client issues JWTs with a 300-second TTL. Langflow's
`otel25-mcp-gateway` MCP server registration stores that JWT as a static
`Authorization` header, so it goes stale within 5 minutes of being set. This
script re-mints a token and PATCHes the registration, intended to run on a
short interval (see sdg/openshift/mcp-token-refresher-cronjob.yaml).

Usage: sdg/scripts/refresh-mcp-token.py

Environment variables:
  KEYCLOAK_URL      https://mcp-keycloak-otel25-gateway.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com
  CLIENT_ID         sdg-pipeline
  CLIENT_SECRET     (required -- no default)
  LANGFLOW_URL      http://langflow-service-backend.otel25-sdg.svc.cluster.local:7860
  LANGFLOW_USERNAME (required)
  LANGFLOW_PASSWORD (required)
  MCP_SERVER_NAME   otel25-mcp-gateway
  MCP_GATEWAY_URL   https://mcp.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com/mcp

Requires: Python 3.9+ stdlib only (urllib, json) -- no third-party packages.
"""

import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

KEYCLOAK_URL = os.environ.get(
    "KEYCLOAK_URL",
    "https://mcp-keycloak-otel25-gateway.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com",
)
CLIENT_ID = os.environ.get("CLIENT_ID", "sdg-pipeline")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")

LANGFLOW_URL = os.environ.get(
    "LANGFLOW_URL", "http://langflow-service-backend.otel25-sdg.svc.cluster.local:7860"
)
LANGFLOW_USERNAME = os.environ.get("LANGFLOW_USERNAME")
LANGFLOW_PASSWORD = os.environ.get("LANGFLOW_PASSWORD")

MCP_SERVER_NAME = os.environ.get("MCP_SERVER_NAME", "otel25-mcp-gateway")
MCP_GATEWAY_URL = os.environ.get(
    "MCP_GATEWAY_URL", "https://mcp.apps.cluster-wfhjs.wfhjs.sandbox1330.opentlc.com/mcp"
)


def fail(message):
    print(f"ERROR: {message}", file=sys.stderr)
    sys.exit(1)


def http_request(url, *, method="GET", data=None, headers=None, form=False):
    headers = dict(headers or {})
    body = None
    if data is not None:
        if form:
            body = "&".join(
                f"{k}={urllib.parse.quote(str(v), safe='')}" for k, v in data.items()
            ).encode()
            headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
        else:
            body = json.dumps(data).encode()
            headers.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return resp.status, json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        return exc.code, {"_raw": detail}


def acquire_jwt():
    if not CLIENT_SECRET:
        fail("CLIENT_SECRET environment variable is required.")
    token_endpoint = f"{KEYCLOAK_URL}/realms/mcp/protocol/openid-connect/token"
    status, body = http_request(
        token_endpoint,
        method="POST",
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
        },
        form=True,
    )
    if status != 200 or "access_token" not in body:
        fail(f"Keycloak token request failed (HTTP {status}): {body}")
    print(f"Acquired JWT from Keycloak ({len(body['access_token'])} chars)")
    return body["access_token"]


def login_langflow():
    if not LANGFLOW_USERNAME or not LANGFLOW_PASSWORD:
        fail("LANGFLOW_USERNAME and LANGFLOW_PASSWORD environment variables are required.")
    status, body = http_request(
        f"{LANGFLOW_URL}/api/v1/login",
        method="POST",
        data={"username": LANGFLOW_USERNAME, "password": LANGFLOW_PASSWORD},
        form=True,
    )
    if status != 200 or "access_token" not in body:
        fail(f"Langflow login failed (HTTP {status}): {body}")
    print("Logged into Langflow API")
    return body["access_token"]


def update_mcp_server(langflow_token, jwt):
    status, body = http_request(
        f"{LANGFLOW_URL}/api/v2/mcp/servers/{MCP_SERVER_NAME}",
        method="PATCH",
        data={"url": MCP_GATEWAY_URL, "headers": {"Authorization": f"Bearer {jwt}"}},
        headers={"Authorization": f"Bearer {langflow_token}"},
    )
    if status != 200:
        fail(f"Langflow MCP server PATCH failed (HTTP {status}): {body}")
    print(f"Updated Langflow MCP server '{MCP_SERVER_NAME}' with a fresh token")


def main():
    jwt = acquire_jwt()
    langflow_token = login_langflow()
    update_mcp_server(langflow_token, jwt)
    print("OK")


if __name__ == "__main__":
    main()
