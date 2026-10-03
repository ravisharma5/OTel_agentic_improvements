"""Tests for the mtime-polling ConfigMap file-watcher pattern.

Validates the watcher algorithm that the conversion CLI bakes into every
generated scaffold (per D-16). Uses a minimal watcher implementation that
mirrors the generated scaffold's behavior: daemon thread, mtime check,
threading.Lock for URL access, URL validation, and httpx client base_url
mutation.

The watcher polls at 0.2-second intervals (for test speed; generated
scaffolds use 5-second intervals in production).
"""

from __future__ import annotations

import os
import tempfile
import threading
import time
from pathlib import Path

import httpx
import pytest


# ---------------------------------------------------------------------------
# Minimal ConfigMap watcher implementation (mirrors generated scaffold)
# ---------------------------------------------------------------------------

class ConfigMapWatcher:
    """Mtime-polling ConfigMap file-watcher for backend URL routing.

    Mirrors the watcher baked into generated scaffolds by openapi_to_mcp.py.
    Polls the file's mtime at a configurable interval, validates URL format,
    and optionally mutates an httpx.AsyncClient's base_url property.
    """

    def __init__(
        self,
        config_path: str,
        default_url: str = "http://localhost:4010",
        poll_interval: float = 0.2,
        client: httpx.AsyncClient | None = None,
    ):
        self._config_path = Path(config_path)
        self._lock = threading.Lock()
        self._url = default_url
        self._poll_interval = poll_interval
        self._client = client
        self._last_mtime: float = 0.0
        self._thread: threading.Thread | None = None

    @property
    def url(self) -> str:
        with self._lock:
            return self._url

    def _load_url(self) -> None:
        """Read URL from file, validate, and update state."""
        try:
            raw = self._config_path.read_text().strip()
            if raw and (raw.startswith("http://") or raw.startswith("https://")):
                with self._lock:
                    self._url = raw
                if self._client is not None:
                    self._client.base_url = raw
        except FileNotFoundError:
            pass  # keep current URL on missing file

    def _poll(self) -> None:
        while True:
            try:
                current_mtime = self._config_path.stat().st_mtime
                if current_mtime != self._last_mtime:
                    self._last_mtime = current_mtime
                    self._load_url()
            except FileNotFoundError:
                pass
            time.sleep(self._poll_interval)

    def start(self) -> None:
        """Start the polling daemon thread."""
        # Do an initial load if the file exists
        self._load_url()
        self._thread = threading.Thread(target=self._poll, daemon=True)
        self._thread.start()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_detects_file_change():
    """Write an initial URL, start the watcher, overwrite with a new URL,
    assert the new URL is picked up within 2 seconds."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("http://old-backend:4010")
        f.flush()
        tmp_path = f.name

    try:
        watcher = ConfigMapWatcher(config_path=tmp_path)
        watcher.start()
        time.sleep(0.1)
        assert watcher.url == "http://old-backend:4010"

        # Overwrite with new URL
        Path(tmp_path).write_text("http://new-backend:4010")

        # Wait for detection (up to 2 seconds)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if watcher.url == "http://new-backend:4010":
                break
            time.sleep(0.05)

        assert watcher.url == "http://new-backend:4010"
    finally:
        os.unlink(tmp_path)


def test_handles_missing_file():
    """Start the watcher when the file does not exist; assert no crash
    and the default URL is used."""
    nonexistent = os.path.join(tempfile.gettempdir(), "does_not_exist_12345.txt")
    # Ensure it really doesn't exist
    if os.path.exists(nonexistent):
        os.unlink(nonexistent)

    watcher = ConfigMapWatcher(
        config_path=nonexistent,
        default_url="http://default-backend:4010",
    )
    watcher.start()
    time.sleep(0.5)

    assert watcher.url == "http://default-backend:4010"


def test_rejects_invalid_url():
    """Write 'not-a-url' to the file; assert the watcher keeps the
    previous valid URL (per T-02-04: validate URL starts with http://
    or https://)."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("http://valid-backend:4010")
        f.flush()
        tmp_path = f.name

    try:
        watcher = ConfigMapWatcher(config_path=tmp_path)
        watcher.start()
        time.sleep(0.1)
        assert watcher.url == "http://valid-backend:4010"

        # Write invalid URL
        Path(tmp_path).write_text("not-a-url")

        # Wait a bit for the watcher to see the change
        time.sleep(0.5)

        # Should still have the old valid URL
        assert watcher.url == "http://valid-backend:4010"
    finally:
        os.unlink(tmp_path)


def test_updates_httpx_client_base_url():
    """Create an httpx.AsyncClient with base_url, start the watcher
    passing the client reference, change the file, and assert that
    client.base_url reflects the new value.

    This proves the httpx client attribute is mutable and the watcher
    updates it correctly in isolation. Note: whether FastMCP
    from_openapi() re-reads client.base_url per-request remains
    unverified and is deferred to Phase 3 (see STATE.md).
    """
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write("http://old-backend:4010")
        f.flush()
        tmp_path = f.name

    try:
        client = httpx.AsyncClient(base_url="http://old-backend:4010")

        watcher = ConfigMapWatcher(
            config_path=tmp_path,
            client=client,
        )
        watcher.start()
        time.sleep(0.1)

        # Overwrite with new URL
        Path(tmp_path).write_text("http://new-backend:4010")

        # Wait for detection (up to 2 seconds)
        deadline = time.monotonic() + 2.0
        while time.monotonic() < deadline:
            if "new-backend" in str(client.base_url):
                break
            time.sleep(0.05)

        # httpx base_url property assignment preserves the URL as-is
        # (constructor adds trailing slash, but setter may not -- depends
        # on httpx version). Compare normalized string.
        assert str(client.base_url).rstrip("/") == "http://new-backend:4010"
    finally:
        os.unlink(tmp_path)
