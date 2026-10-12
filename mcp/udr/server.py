# UDR MCP Server -- TS 29.504/29.505 Nudr_DataRepository (1 tool)
#
# Explicit @mcp.tool() server rather than from_openapi(), matching the
# pattern already used for mcp/nwdaf and mcp/camara.
#
# Spec covered:
#   - Nudr_DataRepository, authentication-subscription resource
#     (GET /subscription-data/{ueId}/authentication-data/authentication-subscription) -- 1 tool
#
#   Scoped to this one operation deliberately: it's the only Nudr operation
#   confirmed returning real data against the live NextGCore deployment this
#   tool targets. provisioned-data/am-data exists in the spec and returns a
#   valid 200, but comes back empty ({}) because the test subscriber used to
#   confirm reachability was only provisioned with security data, not
#   AM-subscription/slice info -- not exposed as a tool yet since there's
#   nothing to return.
#
# Backend routing:
#   UDR_BASE_URL ConfigMap key, host:port only (no path component).
#   The tool function appends the API-relative path in code.
#
# Transport selection:
#   UDR_PROTOCOL ConfigMap key selects the HTTP transport, same convention
#   as NWDAF:
#     - "h2c": HTTP/2 cleartext prior-knowledge (NextGCore's UDR requires this)
#     - "http1.1": standard HTTP/1.1 (Prism or other HTTP/1.1 backends)
#   When the ConfigMap watcher detects a protocol change, the client is
#   closed and recreated with the appropriate transport.
#
# NextGCore path divergence:
#   NextGCore's UDR serves the full path /nudr-dr/v2/subscription-data/...
#   For Prism (if a mock is ever stood up for this spec), the operator
#   updates UDR_BASE_URL to add the server base path the same way NWDAF's
#   ConfigMap comment describes for AnalyticsInfo vs. NextGCore.
#
# ConfigMap change detection:
#   SHA-256 content hashing rather than st_mtime, same reasoning as NWDAF's
#   server.py -- Kubernetes ConfigMap volume updates are atomic symlink
#   swaps, and st_mtime on the resolved file isn't reliably updated across
#   every CRI/storage driver combination.
#
# h2c client implementation note:
#   httpx2.AsyncClient wrapping a raw httpcore2.AsyncConnectionPool as its
#   transport (the pattern NWDAF's server.py uses for its own h2c branch)
#   hits a real bug in httpx2==2.13.1/httpcore2==2.13.1 (the versions this
#   server locks, matching NWDAF's own lockfile): httpcore2's connection
#   pool calls request.url.scheme.decode() on a value httpx2 already passes
#   as a str, raising AttributeError on every request. Confirmed live
#   against this exact UDR instance. _H2CClient below drives httpcore2's
#   pool directly instead, bypassing httpx2's broken translation layer --
#   the same approach that got real responses out of UDR/UDM/AUSF during
#   this feature's live investigation. NWDAF's own h2c path has this same
#   bug; not fixed here since it's out of scope for this change, flagged
#   separately.

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
logger = logging.getLogger("mcp-udr")


# --- ConfigMap file paths (BACK-03 contract) ---
BACKEND_ROUTING_PATH = os.environ.get(
    "BACKEND_ROUTING_FILE", "/config/backend-routing/UDR_BASE_URL"
)
UDR_PROTOCOL_PATH = os.environ.get(
    "UDR_PROTOCOL_FILE", "/config/backend-routing/UDR_PROTOCOL"
)

# --- Mutable state (protected by _backend_url_lock) ---
_backend_url_lock = threading.Lock()
_backend_url = os.environ.get(
    "UDR_BASE_URL", "http://localhost:4010"
)  # fallback for local dev
_current_protocol = os.environ.get("UDR_PROTOCOL", "http1.1")


class _H2CResponse:
    """Minimal response wrapper matching the subset of httpx2.Response this server uses."""

    def __init__(self, status_code: int, body: bytes):
        self.status_code = status_code
        self._body = body

    @property
    def text(self) -> str:
        return self._body.decode("utf-8", errors="replace")

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}: {self.text}")


class _H2CClient:
    """Thin async client over a raw httpcore2.AsyncConnectionPool for h2c prior-knowledge.

    See the module docstring's "h2c client implementation note" for why this
    exists instead of httpx2.AsyncClient(transport=httpcore2.AsyncConnectionPool(...)).
    """

    def __init__(self, base_url: str):
        self._base_url = base_url.rstrip("/")
        self._pool = httpcore2.AsyncConnectionPool(http1=False, http2=True)

    async def get(self, path: str, params: dict | None = None) -> _H2CResponse:
        url = f"{self._base_url}{path}"
        if params:
            import urllib.parse
            url += "?" + urllib.parse.urlencode(params)
        response = await self._pool.request("GET", url)
        body = await response.aread()
        return _H2CResponse(response.status, body)

    async def aclose(self) -> None:
        await self._pool.aclose()


def _create_client(base_url: str, protocol: str):
    """Create a client with transport selected by protocol.

    Args:
        base_url: The base URL for the backend (host:port, possibly with path).
        protocol: Transport selection -- "h2c" for HTTP/2 cleartext prior-knowledge,
                  "http1.1" (or anything else) for standard HTTP/1.1.

    Returns:
        An _H2CClient for "h2c", or an httpx2.AsyncClient for "http1.1".
    """
    if protocol == "h2c":
        logger.info("Creating h2c (HTTP/2 cleartext) client for %s", base_url)
        return _H2CClient(base_url)
    else:
        # Default HTTP/1.1 transport (works with Prism and other HTTP/1.1 backends).
        logger.info("Creating HTTP/1.1 client for %s", base_url)
        return httpx2.AsyncClient(base_url=base_url)


def _load_backend_url():
    """Read backend URL and protocol from ConfigMap-mounted files.

    Validates URLs start with http:// or https:// (T-03-05 mitigation).
    When URL or protocol changes, closes the old client and recreates it
    with the appropriate transport.
    """
    global _backend_url, _current_protocol, client

    url_changed = False
    protocol_changed = False

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

    try:
        protocol = Path(UDR_PROTOCOL_PATH).read_text().strip()
        if protocol:
            with _backend_url_lock:
                if _current_protocol != protocol:
                    _current_protocol = protocol
                    protocol_changed = True
                    logger.info("Protocol updated: %s", protocol)
    except FileNotFoundError:
        logger.debug("Protocol file not found at %s, using default", UDR_PROTOCOL_PATH)

    if url_changed or protocol_changed:
        old_client = client
        with _backend_url_lock:
            new_url = _backend_url
            new_protocol = _current_protocol
        client = _create_client(new_url, new_protocol)
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(old_client.aclose())
            else:
                loop.run_until_complete(old_client.aclose())
        except Exception:
            logger.debug("Could not close old client (may already be closed)")


def get_backend_url() -> str:
    """Return current backend URL under lock."""
    with _backend_url_lock:
        return _backend_url


def _compute_file_hash(path: Path) -> str | None:
    """Compute SHA-256 hash of file contents. Returns None on error."""
    try:
        return hashlib.sha256(path.read_bytes()).hexdigest()
    except (FileNotFoundError, PermissionError, OSError):
        return None


def _start_config_watcher():
    """Poll ConfigMap-mounted files for changes (content-hash-based).

    Same approach as NWDAF's server.py: SHA-256 content hashing plus
    os.path.realpath() as a secondary signal for symlink rotation, since
    st_mtime on a ConfigMap-mounted file isn't a reliable change signal.
    """
    watched_paths = [
        Path(BACKEND_ROUTING_PATH),
        Path(UDR_PROTOCOL_PATH),
    ]

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

                current_hash = _compute_file_hash(p)
                if current_hash is not None and current_hash != last_hashes.get(key):
                    last_hashes[key] = current_hash
                    changed = True
                    logger.debug("Content hash changed for %s", key)

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


# --- HTTP client (protocol-aware transport) ---
client = _create_client(get_backend_url(), _current_protocol)


# --- FastMCP Server ---
mcp = FastMCP("mcp-udr")


@mcp.tool()
async def get_authentication_subscription(supi: str) -> str:
    """Retrieve a subscriber's authentication subscription data from UDR.

    Returns the 3GPP authentication vector material and sequence-number
    state UDR holds for a subscriber: authentication method, encrypted
    permanent key (K), encrypted OPc key, authentication management field,
    and the current SQN scheme/value. Useful for diagnosing authentication
    failures or confirming a subscriber's auth configuration during an
    investigation.

    Args:
        supi: Subscription Permanent Identifier, formatted "imsi-<imsi>"
            for an IMSI-based SUPI (e.g. "imsi-999700000000001").

    Returns:
        JSON string with the subscriber's authentication subscription data.
    """
    # API-relative path appended in code -- ConfigMap UDR_BASE_URL is host:port only.
    response = await client.get(
        f"/subscription-data/{supi}/authentication-data/authentication-subscription"
    )
    if response.status_code == 404:
        return json.dumps({"status": "not_found", "message": f"No authentication subscription data for {supi}"})
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
    """Run the UDR MCP server."""
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
