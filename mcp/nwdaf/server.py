# NWDAF MCP Server -- TS 29.520 Analytics & Events (3 tools from 2 specs)
#
# Per D-10a: multi-spec domains use explicit @mcp.tool() decorators instead of
# from_openapi() to avoid MCPServerRegistration tool-name double-prefixing.
#
# Specs covered:
#   - Nnwdaf_AnalyticsInfo (GET /analytics) -- 1 tool
#   - Nnwdaf_EventsSubscription (POST /subscriptions, DELETE /subscriptions/{id}) -- 2 tools
#
# Backend routing:
#   AnalyticsInfo uses NWDAF_BASE_URL ConfigMap key.
#   EventsSubscription uses NWDAF_EVENTS_BASE_URL ConfigMap key (Phase 4, D-15).
#   The ConfigMap provides host:port ONLY (no path component).
#   Tool functions MUST append API-relative paths in code.
#
# Transport selection (Phase 4, D-15):
#   NWDAF_PROTOCOL ConfigMap key selects the HTTP transport:
#     - "h2c": HTTP/2 cleartext prior-knowledge (for NextGCore)
#     - "http1.1": standard HTTP/1.1 (for Prism or other HTTP/1.1 backends)
#   When the ConfigMap watcher detects a protocol change, the client is
#   closed and recreated with the appropriate transport.
#
# NextGCore path divergence:
#   Prism strips the OpenAPI servers base path -- serves analytics at /analytics.
#   NextGCore uses the full path /nnwdaf-analyticsinfo/v1/analytics.
#   For Prism (D-11 verification target), appending /analytics to host:port works.
#   For NextGCore, the operator would update ConfigMap NWDAF_BASE_URL to include
#   the server base path (e.g., http://nextgcore:7777/nnwdaf-analyticsinfo/v1).
#
#   The EventsSubscription spec uses a DIFFERENT server base path
#   (/nnwdaf-eventssubscription/v1) than AnalyticsInfo (/nnwdaf-analyticsinfo/v1).
#   For Prism, both serve at root, so a single NWDAF_BASE_URL works.
#   For NextGCore, NWDAF_EVENTS_BASE_URL carries the EventsSubscription base path
#   (e.g., http://nextgcore:7777/nnwdaf-eventssubscription/v1).
#
# ConfigMap change detection (Phase 4):
#   Uses SHA-256 content hashing instead of st_mtime. Kubernetes updates
#   ConfigMap volumes via atomic symlink swaps (..data -> ..2024_01_01_12_00_00),
#   and st_mtime on the resolved file does not always change reliably depending
#   on CRI and storage driver. Content hashing is always reliable.
#   os.path.realpath() comparison is used as a secondary signal to detect
#   symlink rotation even if content hash computation fails.

import hashlib
import json
import logging
import os
import threading
import time
from pathlib import Path

import httpcore2
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
logger = logging.getLogger("mcp-nwdaf")


# --- ConfigMap file paths (BACK-03 contract) ---
BACKEND_ROUTING_PATH = os.environ.get(
    "BACKEND_ROUTING_FILE", "/config/backend-routing/NWDAF_BASE_URL"
)
NWDAF_PROTOCOL_PATH = os.environ.get(
    "NWDAF_PROTOCOL_FILE", "/config/backend-routing/NWDAF_PROTOCOL"
)
NWDAF_EVENTS_ROUTING_PATH = os.environ.get(
    "NWDAF_EVENTS_ROUTING_FILE", "/config/backend-routing/NWDAF_EVENTS_BASE_URL"
)

# --- Mutable state (protected by _backend_url_lock) ---
_backend_url_lock = threading.Lock()
_backend_url = os.environ.get(
    "NWDAF_BASE_URL", "http://localhost:4010"
)  # fallback for local dev
_current_protocol = os.environ.get("NWDAF_PROTOCOL", "http1.1")
_nwdaf_events_url = os.environ.get(
    "NWDAF_EVENTS_BASE_URL", "http://localhost:4010"
)  # fallback for local dev


def _create_client(base_url: str, protocol: str) -> httpx2.AsyncClient:
    """Create an httpx2 AsyncClient with transport selected by protocol.

    Args:
        base_url: The base URL for the backend (host:port, possibly with path).
        protocol: Transport selection -- "h2c" for HTTP/2 cleartext prior-knowledge,
                  "http1.1" (or anything else) for standard HTTP/1.1.

    Returns:
        An httpx2.AsyncClient configured with the appropriate transport.
    """
    if protocol == "h2c":
        # Prior-knowledge mode: disable HTTP/1.1, force HTTP/2.
        # Sends the HTTP/2 connection preface directly on cleartext connections.
        transport = httpcore2.AsyncConnectionPool(http1=False, http2=True)
        logger.info("Creating h2c (HTTP/2 cleartext) client for %s", base_url)
        return httpx2.AsyncClient(base_url=base_url, transport=transport)
    else:
        # Default HTTP/1.1 transport (works with Prism and other HTTP/1.1 backends).
        logger.info("Creating HTTP/1.1 client for %s", base_url)
        return httpx2.AsyncClient(base_url=base_url)


def _load_backend_url():
    """Read backend URL, events URL, and protocol from ConfigMap-mounted files.

    Validates URLs start with http:// or https:// (T-03-05 mitigation).
    When URL or protocol changes, closes the old client and recreates it
    with the appropriate transport. Also handles events URL changes.
    """
    global _backend_url, _current_protocol, _nwdaf_events_url, client, events_client

    url_changed = False
    protocol_changed = False
    events_url_changed = False

    # Read the analytics backend URL
    try:
        url = Path(BACKEND_ROUTING_PATH).read_text().strip()
        if url and (url.startswith("http://") or url.startswith("https://")):
            with _backend_url_lock:
                if _backend_url != url:
                    _backend_url = url
                    url_changed = True
                    logger.info("Backend URL updated: %s", url)
        elif url:
            logger.warning("Invalid backend URL (must start with http:// or https://): %s", url)
    except FileNotFoundError:
        logger.debug("ConfigMap file not found at %s, using default", BACKEND_ROUTING_PATH)

    # Read the protocol selection
    try:
        protocol = Path(NWDAF_PROTOCOL_PATH).read_text().strip()
        if protocol:
            with _backend_url_lock:
                if _current_protocol != protocol:
                    _current_protocol = protocol
                    protocol_changed = True
                    logger.info("Protocol updated: %s", protocol)
    except FileNotFoundError:
        logger.debug("Protocol file not found at %s, using default", NWDAF_PROTOCOL_PATH)

    # Read the events backend URL
    try:
        events_url = Path(NWDAF_EVENTS_ROUTING_PATH).read_text().strip()
        if events_url and (events_url.startswith("http://") or events_url.startswith("https://")):
            with _backend_url_lock:
                if _nwdaf_events_url != events_url:
                    _nwdaf_events_url = events_url
                    events_url_changed = True
                    logger.info("Events backend URL updated: %s", events_url)
        elif events_url:
            logger.warning("Invalid events backend URL (must start with http:// or https://): %s", events_url)
    except FileNotFoundError:
        logger.debug("Events ConfigMap file not found at %s, using default", NWDAF_EVENTS_ROUTING_PATH)

    # Recreate analytics client if URL or protocol changed
    if url_changed or protocol_changed:
        old_client = client
        with _backend_url_lock:
            new_url = _backend_url
            new_protocol = _current_protocol
        client = _create_client(new_url, new_protocol)
        try:
            # Schedule old client closure (best-effort in sync context)
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(old_client.aclose())
            else:
                loop.run_until_complete(old_client.aclose())
        except Exception:
            logger.debug("Could not close old analytics client (may already be closed)")

    # Recreate events client if events URL or protocol changed
    if events_url_changed or protocol_changed:
        old_events_client = events_client
        with _backend_url_lock:
            new_events_url = _nwdaf_events_url
            new_protocol = _current_protocol
        events_client = _create_client(new_events_url, new_protocol)
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(old_events_client.aclose())
            else:
                loop.run_until_complete(old_events_client.aclose())
        except Exception:
            logger.debug("Could not close old events client (may already be closed)")


def get_backend_url() -> str:
    """Return current analytics backend URL under lock."""
    with _backend_url_lock:
        return _backend_url


def get_events_backend_url() -> str:
    """Return current events backend URL under lock."""
    with _backend_url_lock:
        return _nwdaf_events_url


def _compute_file_hash(path: Path) -> str | None:
    """Compute SHA-256 hash of file contents. Returns None on error."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (FileNotFoundError, PermissionError, OSError):
        return None


def _start_config_watcher():
    """Poll ConfigMap-mounted files for changes (content-hash-based).

    Uses SHA-256 content hashing instead of mtime because Kubernetes
    updates ConfigMap volumes via atomic symlink swaps, and st_mtime
    on the resolved file does not always change reliably depending on
    CRI and storage driver.

    Also tracks os.path.realpath() as a secondary signal to detect
    symlink rotation even if content hash computation fails.
    """
    watched_paths = [
        Path(BACKEND_ROUTING_PATH),
        Path(NWDAF_PROTOCOL_PATH),
        Path(NWDAF_EVENTS_ROUTING_PATH),
    ]

    # Initialize content hashes and realpath targets
    last_hashes: dict[str, str | None] = {}
    last_realpaths: dict[str, str | None] = {}
    for p in watched_paths:
        last_hashes[str(p)] = _compute_file_hash(p)
        try:
            last_realpaths[str(p)] = os.path.realpath(str(p))
        except OSError:
            last_realpaths[str(p)] = None

    def _poll():
        nonlocal last_hashes, last_realpaths
        while True:
            changed = False
            for p in watched_paths:
                key = str(p)

                # Primary signal: content hash
                current_hash = _compute_file_hash(p)
                if current_hash is not None and current_hash != last_hashes.get(key):
                    last_hashes[key] = current_hash
                    changed = True
                    logger.debug("Content hash changed for %s", key)

                # Secondary signal: realpath (symlink target)
                try:
                    current_realpath = os.path.realpath(str(p))
                except OSError:
                    current_realpath = None
                if current_realpath is not None and current_realpath != last_realpaths.get(key):
                    last_realpaths[key] = current_realpath
                    if not changed:
                        changed = True
                        logger.debug("Symlink target changed for %s", key)

            if changed:
                _load_backend_url()

            time.sleep(5)  # poll every 5 seconds

    t = threading.Thread(target=_poll, daemon=True)
    t.start()


# --- HTTP clients (analytics + events, with protocol-aware transport) ---
client = _create_client(get_backend_url(), _current_protocol)
events_client = _create_client(get_events_backend_url(), _current_protocol)


# --- FastMCP Server ---
mcp = FastMCP("mcp-nwdaf")


@mcp.tool()
async def get_nwdaf_analytics(event_id: str = "NF_LOAD") -> str:
    """Query NWDAF analytics data for a specific event type.

    Supported event types include NF_LOAD, LOAD_LEVEL_INFORMATION,
    NETWORK_PERFORMANCE, SERVICE_EXPERIENCE, UE_MOBILITY, UE_COMMUNICATION,
    QOS_SUSTAINABILITY, ABNORMAL_BEHAVIOUR, USER_DATA_CONGESTION, NSI_LOAD_LEVEL.

    Args:
        event_id: The analytics event type to query (default: NF_LOAD).

    Returns:
        JSON string containing analytics data from the NWDAF backend.
    """
    # API-relative path appended in code -- ConfigMap NWDAF_BASE_URL is host:port only.
    # For Prism: base_url=http://prism:4010, path=/analytics -> http://prism:4010/analytics
    # For NextGCore: operator updates ConfigMap to include server base path.
    response = await client.get("/analytics", params={"event-id": event_id})
    if response.status_code == 204:
        return json.dumps({"status": "no_content", "message": "No analytics data available for the requested event type"})
    response.raise_for_status()
    return response.text


@mcp.tool()
async def subscribe_nwdaf_events(event_id: str, notification_uri: str) -> str:
    """Subscribe to NWDAF analytics event notifications.

    The notification URI receives callbacks when analytics data changes.
    Creates an event subscription for the specified analytics event type.

    Args:
        event_id: The analytics event type to subscribe to (e.g., NF_LOAD, UE_MOBILITY).
        notification_uri: The URI that will receive notification callbacks.

    Returns:
        JSON string containing the created subscription details including subscription ID.
    """
    # Uses events_client with NWDAF_EVENTS_BASE_URL for correct path routing.
    # NextGCore EventsSubscription uses /nnwdaf-eventssubscription/v1 base path.
    body = {
        "eventSubscriptions": [
            {"event": event_id}
        ],
        "notificationURI": notification_uri,
    }
    response = await events_client.post("/subscriptions", json=body)
    response.raise_for_status()
    return response.text


@mcp.tool()
async def unsubscribe_nwdaf_events(subscription_id: str) -> str:
    """Unsubscribe from NWDAF analytics event notifications by subscription ID.

    Removes an existing event subscription, stopping further notification callbacks.

    Args:
        subscription_id: The ID of the subscription to remove.

    Returns:
        Confirmation message indicating the subscription was deleted.
    """
    # Uses events_client with NWDAF_EVENTS_BASE_URL for correct path routing.
    response = await events_client.delete(f"/subscriptions/{subscription_id}")
    if response.status_code == 204:
        return json.dumps({"status": "deleted", "subscription_id": subscription_id})
    response.raise_for_status()
    return response.text


# --- Health endpoint ---
async def healthz(request: Request) -> PlainTextResponse:
    """Liveness/readiness probe for OpenShift."""
    return PlainTextResponse("ok")


# --- App factory ---
def create_app():
    """Create the ASGI app with MCP and health routes."""
    _load_backend_url()
    _start_config_watcher()

    app = mcp.http_app()
    app.router.routes.append(Route("/healthz", healthz))
    return app


def main():
    """Run the NWDAF MCP server."""
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
