# CAMARA Device Status MCP Server -- 3 tools from 3 specs
#
# Separate from mcp/camara/ (CAMARA Device Location) even though both are CAMARA
# projects: Device Status comes from a different upstream repo
# (camaraproject/DeviceStatus vs camaraproject/DeviceLocation), ships 3 independent
# query APIs rather than 2, and each needs its own Prism backend/ConfigMap key.
# Folding all 5 operations into one server.py would mean 5 ConfigMap watchers and
# 5 httpx2 clients in a single file -- a new domain-server directory, matching how
# NWDAF and the TMF servers each get their own directory, keeps each file focused.
#
# Multi-spec domains use explicit @mcp.tool() decorators instead of from_openapi()
# to avoid MCPServerRegistration tool-name double-prefixing (same approach as
# mcp/camara/ and mcp/nwdaf/).
#
# Specs covered (all three are narrow, single-operation CAMARA Device Status APIs):
#   - Device Roaming Status (POST /retrieve)       -- uses CAMARA_ROAMING_BASE_URL
#   - Device Reachability Status (POST /retrieve)  -- uses CAMARA_REACHABILITY_BASE_URL
#   - Connected Network Type (POST /retrieve)      -- uses CAMARA_NETWORK_TYPE_BASE_URL
#
# Backend: no live telco operator backend is available for CAMARA Device Status in
# this project (unlike NWDAF's NextGCore reference core). Backed by three separate
# Prism mock instances, following the same pattern as CAMARA Device Location.
# Each operation's OpenAPI spec already ships realistic named `examples` for every
# response (e.g. roaming by country code, reachability by connectivity type) --
# checked before building, since Phase 4 found generic Prism dynamic-mode output
# unusably generic for other specs. No enrichment was needed here.

import logging
import os
import threading
import time
from pathlib import Path

import httpx2
import uvicorn
from fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import PlainTextResponse
from starlette.routing import Route

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("mcp-camara-device-status")


def _make_backend(name: str, env_var: str, routing_file_env: str, default_path: str, default_port: int):
    """Create a ConfigMap-watched backend URL holder plus its httpx2 client.

    Returns (get_url, load_url, start_watcher, client) for one backend. Mirrors the
    dual-watcher pattern in mcp/camara/server.py, generalized to N backends since
    Device Status has three independent Prism instances instead of two.
    """
    routing_path = os.environ.get(routing_file_env, default_path)
    lock = threading.Lock()
    state = {"url": os.environ.get(env_var, f"http://localhost:{default_port}")}

    client = httpx2.AsyncClient(
        base_url=state["url"],
        headers={"Authorization": "Bearer prism-mock-token"},
    )

    def load_url():
        """Read backend URL from ConfigMap-mounted file.

        Validates URL starts with http:// or https:// before applying it.
        """
        try:
            url = Path(routing_path).read_text().strip()
            if url and (url.startswith("http://") or url.startswith("https://")):
                with lock:
                    state["url"] = url
                client.base_url = url
                logger.info("%s backend URL updated: %s", name, url)
            elif url:
                logger.warning(
                    "Invalid %s URL (must start with http:// or https://): %s", name, url
                )
        except FileNotFoundError:
            logger.debug("ConfigMap file not found at %s, using default", routing_path)

    def get_url() -> str:
        with lock:
            return state["url"]

    def start_watcher():
        """Poll ConfigMap-mounted backend URL file for changes (mtime-based)."""
        config_path = Path(routing_path)
        last_mtime = 0.0

        def _poll():
            nonlocal last_mtime
            while True:
                try:
                    current_mtime = config_path.stat().st_mtime
                    if current_mtime != last_mtime:
                        last_mtime = current_mtime
                        load_url()
                except FileNotFoundError:
                    pass
                time.sleep(5)

        t = threading.Thread(target=_poll, daemon=True)
        t.start()

    return get_url, load_url, start_watcher, client


# --- Backend setup: one ConfigMap watcher + httpx2 client per Device Status API ---
_, _load_roaming_url, _start_roaming_watcher, roaming_client = _make_backend(
    "roaming",
    "CAMARA_ROAMING_BASE_URL",
    "ROAMING_ROUTING_FILE",
    "/config/backend-routing/CAMARA_ROAMING_BASE_URL",
    4010,
)
_, _load_reachability_url, _start_reachability_watcher, reachability_client = _make_backend(
    "reachability",
    "CAMARA_REACHABILITY_BASE_URL",
    "REACHABILITY_ROUTING_FILE",
    "/config/backend-routing/CAMARA_REACHABILITY_BASE_URL",
    4011,
)
_, _load_network_type_url, _start_network_type_watcher, network_type_client = _make_backend(
    "network-type",
    "CAMARA_NETWORK_TYPE_BASE_URL",
    "NETWORK_TYPE_ROUTING_FILE",
    "/config/backend-routing/CAMARA_NETWORK_TYPE_BASE_URL",
    4012,
)


# --- FastMCP Server ---
mcp = FastMCP("mcp-camara-device-status")


def _device_identifier(device_phone_number: str) -> dict:
    """Build the CAMARA `device` object for a phone-number-identified device."""
    return {"phoneNumber": device_phone_number}


@mcp.tool()
async def get_roaming_status(device_phone_number: str) -> str:
    """Get a device's current roaming status and visited country information.

    Uses the CAMARA Device Roaming Status API. Returns whether the device is
    roaming and, if so, the visited country's mobile country code and ISO
    country codes.

    Args:
        device_phone_number: Phone number of the device to check (e.g., "+123456789").

    Returns:
        JSON string with roaming status (roaming, countryCode, countryName, lastStatusTime).
    """
    body = {"device": _device_identifier(device_phone_number)}
    response = await roaming_client.post("/retrieve", json=body)
    response.raise_for_status()
    return response.text


@mcp.tool()
async def get_reachability_status(device_phone_number: str) -> str:
    """Get a device's current network reachability status.

    Uses the CAMARA Device Reachability Status API. Returns whether the device
    is reachable from the network and, if so, via which connectivity types
    (DATA, SMS, or both).

    Args:
        device_phone_number: Phone number of the device to check (e.g., "+123456789").

    Returns:
        JSON string with reachability status (reachable, connectivity, lastStatusTime).
    """
    body = {"device": _device_identifier(device_phone_number)}
    response = await reachability_client.post("/retrieve", json=body)
    response.raise_for_status()
    return response.text


@mcp.tool()
async def get_connected_network_type(device_phone_number: str) -> str:
    """Get the mobile network technology a device is currently connected to.

    Uses the CAMARA Connected Network Type API. Returns the connected generation
    (2G, 3G, 4G, 5G) or UNKNOWN if it cannot be determined.

    Args:
        device_phone_number: Phone number of the device to check (e.g., "+123456789").

    Returns:
        JSON string with connected network type (connectedNetworkType, lastStatusTime).
    """
    body = {"device": _device_identifier(device_phone_number)}
    response = await network_type_client.post("/retrieve", json=body)
    response.raise_for_status()
    return response.text


# --- Health endpoint ---
async def healthz(request: Request) -> PlainTextResponse:
    """Liveness/readiness probe for OpenShift."""
    return PlainTextResponse("ok")


# --- App factory ---
def create_app():
    """Create the ASGI app with MCP and health routes."""
    _load_roaming_url()
    _load_reachability_url()
    _load_network_type_url()
    _start_roaming_watcher()
    _start_reachability_watcher()
    _start_network_type_watcher()

    app = mcp.http_app()
    app.router.routes.append(Route("/healthz", healthz))
    return app


def main():
    """Run the CAMARA Device Status MCP server."""
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
