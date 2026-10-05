# CAMARA Device Location MCP Server -- 2 tools from 2 specs
#
# Per D-10a: multi-spec domains use explicit @mcp.tool() decorators instead of
# from_openapi() to avoid MCPServerRegistration tool-name double-prefixing.
#
# Specs covered:
#   - Device Location Verification (POST /verify) -- 1 tool, uses CAMARA_BASE_URL
#   - Device Location Retrieval (POST /retrieve) -- 1 tool, uses CAMARA_RETRIEVAL_BASE_URL
#
# Backend routing:
#   Unlike NWDAF, CAMARA uses TWO separate backend URLs because verify and retrieve
#   hit separate Prism instances (separate OpenAPI specs served on separate ports).
#   Each has its own ConfigMap file-watcher and httpx2.AsyncClient.

import json
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
logger = logging.getLogger("mcp-camara")


# --- ConfigMap file-watcher for CAMARA_BASE_URL (verify backend) ---
VERIFY_ROUTING_PATH = os.environ.get(
    "VERIFY_ROUTING_FILE", "/config/backend-routing/CAMARA_BASE_URL"
)
_verify_url_lock = threading.Lock()
_verify_url = os.environ.get(
    "CAMARA_BASE_URL", "http://localhost:4010"
)  # fallback for local dev


def _load_verify_url():
    """Read verify backend URL from ConfigMap-mounted file.

    Validates URL starts with http:// or https:// (T-03-05 mitigation).
    """
    global _verify_url
    try:
        url = Path(VERIFY_ROUTING_PATH).read_text().strip()
        if url and (url.startswith("http://") or url.startswith("https://")):
            with _verify_url_lock:
                _verify_url = url
            verify_client.base_url = url
            logger.info("Verify backend URL updated: %s", url)
        elif url:
            logger.warning("Invalid verify URL (must start with http:// or https://): %s", url)
    except FileNotFoundError:
        logger.debug("ConfigMap file not found at %s, using default", VERIFY_ROUTING_PATH)


def get_verify_url() -> str:
    """Return current verify backend URL under lock."""
    with _verify_url_lock:
        return _verify_url


def _start_verify_watcher():
    """Poll ConfigMap-mounted verify backend URL file for changes (mtime-based)."""
    config_path = Path(VERIFY_ROUTING_PATH)
    last_mtime = 0.0

    def _poll():
        nonlocal last_mtime
        while True:
            try:
                current_mtime = config_path.stat().st_mtime
                if current_mtime != last_mtime:
                    last_mtime = current_mtime
                    _load_verify_url()
            except FileNotFoundError:
                pass
            time.sleep(5)

    t = threading.Thread(target=_poll, daemon=True)
    t.start()


# --- ConfigMap file-watcher for CAMARA_RETRIEVAL_BASE_URL (retrieve backend) ---
RETRIEVE_ROUTING_PATH = os.environ.get(
    "RETRIEVE_ROUTING_FILE", "/config/backend-routing/CAMARA_RETRIEVAL_BASE_URL"
)
_retrieve_url_lock = threading.Lock()
_retrieve_url = os.environ.get(
    "CAMARA_RETRIEVAL_BASE_URL", "http://localhost:4011"
)  # fallback for local dev (different port)


def _load_retrieve_url():
    """Read retrieve backend URL from ConfigMap-mounted file.

    Validates URL starts with http:// or https:// (T-03-05 mitigation).
    """
    global _retrieve_url
    try:
        url = Path(RETRIEVE_ROUTING_PATH).read_text().strip()
        if url and (url.startswith("http://") or url.startswith("https://")):
            with _retrieve_url_lock:
                _retrieve_url = url
            retrieve_client.base_url = url
            logger.info("Retrieve backend URL updated: %s", url)
        elif url:
            logger.warning("Invalid retrieve URL (must start with http:// or https://): %s", url)
    except FileNotFoundError:
        logger.debug("ConfigMap file not found at %s, using default", RETRIEVE_ROUTING_PATH)


def get_retrieve_url() -> str:
    """Return current retrieve backend URL under lock."""
    with _retrieve_url_lock:
        return _retrieve_url


def _start_retrieve_watcher():
    """Poll ConfigMap-mounted retrieve backend URL file for changes (mtime-based)."""
    config_path = Path(RETRIEVE_ROUTING_PATH)
    last_mtime = 0.0

    def _poll():
        nonlocal last_mtime
        while True:
            try:
                current_mtime = config_path.stat().st_mtime
                if current_mtime != last_mtime:
                    last_mtime = current_mtime
                    _load_retrieve_url()
            except FileNotFoundError:
                pass
            time.sleep(5)

    t = threading.Thread(target=_poll, daemon=True)
    t.start()


# --- HTTP clients (separate clients for verify and retrieve backends) ---
# CAMARA APIs require OAuth2 security. Prism validates security scheme presence
# but does not validate the token value. A dummy Bearer token satisfies Prism's
# security validation. In production, this would be replaced with a real OAuth2 token.
_CAMARA_AUTH_HEADERS = {"Authorization": "Bearer prism-mock-token"}
verify_client = httpx2.AsyncClient(base_url=get_verify_url(), headers=_CAMARA_AUTH_HEADERS)
retrieve_client = httpx2.AsyncClient(base_url=get_retrieve_url(), headers=_CAMARA_AUTH_HEADERS)


# --- FastMCP Server ---
mcp = FastMCP("mcp-camara")


@mcp.tool()
async def verify_location(
    device_phone_number: str,
    latitude: float,
    longitude: float,
    accuracy: float = 100.0,
) -> str:
    """Verify whether a device is at a specific location within an accuracy radius.

    Uses the CAMARA Device Location Verification API. Returns a verification result
    (TRUE, FALSE, or PARTIAL with match rate) indicating whether the device is within
    the specified area.

    Args:
        device_phone_number: Phone number of the device to verify (e.g., "+123456789").
        latitude: Latitude of the location center to verify against.
        longitude: Longitude of the location center to verify against.
        accuracy: Radius in meters defining the verification area (default: 100.0).

    Returns:
        JSON string with verification result (verificationResult, matchRate if PARTIAL).
    """
    body = {
        "device": {
            "phoneNumber": device_phone_number,
        },
        "area": {
            "areaType": "CIRCLE",
            "center": {
                "latitude": latitude,
                "longitude": longitude,
            },
            "radius": accuracy,
        },
    }
    response = await verify_client.post("/verify", json=body)
    response.raise_for_status()
    return response.text


@mcp.tool()
async def retrieve_location(device_phone_number: str) -> str:
    """Retrieve the current location of a device.

    Uses the CAMARA Device Location Retrieval API. Returns the device's current
    location as a geographic area (typically a circle with center coordinates
    and accuracy radius).

    Args:
        device_phone_number: Phone number of the device to locate (e.g., "+123456789").

    Returns:
        JSON string with device location area (latitude, longitude, accuracy).
    """
    body = {
        "device": {
            "phoneNumber": device_phone_number,
        },
    }
    response = await retrieve_client.post("/retrieve", json=body)
    response.raise_for_status()
    return response.text


# --- Health endpoint ---
async def healthz(request: Request) -> PlainTextResponse:
    """Liveness/readiness probe for OpenShift."""
    return PlainTextResponse("ok")


# --- App factory ---
def create_app():
    """Create the ASGI app with MCP and health routes."""
    _load_verify_url()
    _load_retrieve_url()
    _start_verify_watcher()
    _start_retrieve_watcher()

    app = mcp.http_app()
    app.router.routes.append(Route("/healthz", healthz))
    return app


def main():
    """Run the CAMARA MCP server."""
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
