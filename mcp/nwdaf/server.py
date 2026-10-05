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
#   Both specs share the same backend via NWDAF_BASE_URL ConfigMap key.
#   The ConfigMap provides host:port ONLY (no path component).
#   Tool functions MUST append API-relative paths in code.
#
# NextGCore path divergence (Phase 4 forward concern):
#   Prism strips the OpenAPI servers base path -- serves analytics at /analytics.
#   NextGCore uses the full path /nnwdaf-analyticsinfo/v1/analytics.
#   For Prism (D-11 verification target), appending /analytics to host:port works.
#   For NextGCore, the operator would update ConfigMap NWDAF_BASE_URL to include
#   the server base path (e.g., http://nextgcore:7777/nnwdaf-analyticsinfo/v1).
#
#   IMPORTANT: The EventsSubscription spec uses a DIFFERENT server base path
#   (/nnwdaf-eventssubscription/v1) than AnalyticsInfo (/nnwdaf-analyticsinfo/v1).
#   For Prism, both serve at root, so a single NWDAF_BASE_URL works.
#   For NextGCore, a single NWDAF_BASE_URL with the AnalyticsInfo server base path
#   produces incorrect URLs for subscription endpoints. Phase 4 should address this
#   by adding a second ConfigMap key (e.g., NWDAF_EVENTS_BASE_URL) or by including
#   the full path in each tool function with a backend-type discriminator.

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
logger = logging.getLogger("mcp-nwdaf")


# --- ConfigMap file-watcher (BACK-03 contract) ---
BACKEND_ROUTING_PATH = os.environ.get(
    "BACKEND_ROUTING_FILE", "/config/backend-routing/NWDAF_BASE_URL"
)
_backend_url_lock = threading.Lock()
_backend_url = os.environ.get(
    "NWDAF_BASE_URL", "http://localhost:4010"
)  # fallback for local dev


def _load_backend_url():
    """Read backend URL from ConfigMap-mounted file and update state.

    Validates URL starts with http:// or https:// (T-03-05 mitigation).
    On valid URL: updates _backend_url under lock AND mutates client.base_url.
    On invalid URL: keeps previous valid URL.
    """
    global _backend_url
    try:
        url = Path(BACKEND_ROUTING_PATH).read_text().strip()
        if url and (url.startswith("http://") or url.startswith("https://")):
            with _backend_url_lock:
                _backend_url = url
            client.base_url = url
            logger.info("Backend URL updated: %s", url)
        elif url:
            logger.warning("Invalid backend URL (must start with http:// or https://): %s", url)
    except FileNotFoundError:
        logger.debug("ConfigMap file not found at %s, using default", BACKEND_ROUTING_PATH)


def get_backend_url() -> str:
    """Return current backend URL under lock."""
    with _backend_url_lock:
        return _backend_url


def _start_config_watcher():
    """Poll ConfigMap-mounted file for changes (mtime-based).

    Uses mtime polling instead of inotify because Kubernetes
    updates ConfigMap volumes via atomic symlink swaps, which
    do not emit standard IN_MODIFY events.
    """
    config_path = Path(BACKEND_ROUTING_PATH)
    last_mtime = 0.0

    def _poll():
        nonlocal last_mtime
        while True:
            try:
                current_mtime = config_path.stat().st_mtime
                if current_mtime != last_mtime:
                    last_mtime = current_mtime
                    _load_backend_url()
            except FileNotFoundError:
                pass
            time.sleep(5)  # poll every 5 seconds

    t = threading.Thread(target=_poll, daemon=True)
    t.start()


# --- HTTP client (shared across all tools, single backend) ---
client = httpx2.AsyncClient(base_url=get_backend_url())


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
    # API-relative path appended in code -- same reasoning as get_nwdaf_analytics.
    # See module docstring for NextGCore EventsSubscription path divergence note.
    body = {
        "eventSubscriptions": [
            {"event": event_id}
        ],
        "notificationURI": notification_uri,
    }
    response = await client.post("/subscriptions", json=body)
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
    # API-relative path appended in code with path parameter.
    response = await client.delete(f"/subscriptions/{subscription_id}")
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
