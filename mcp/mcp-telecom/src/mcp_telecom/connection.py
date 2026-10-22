"""Connection manager for network devices.

Handles SSH/Telnet connections via Netmiko with connection pooling,
timeouts, and proper cleanup.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

import yaml
from netmiko import NetmikoAuthenticationException, NetmikoTimeoutException

from mcp_telecom.models import DeviceConfig, DeviceInfo, HealthStatus
from mcp_telecom.pool import ConnectionPool

logger = logging.getLogger("mcp_telecom.connection")

# 2026-10-21: confirmed live against the real lab that establishing a fresh
# SSH session to these devices costs 50-75s (SR Linix's CLI is slow to
# present its prompt on a brand-new login) -- and connect() below used to
# open and immediately close a connection on every single tool call, paying
# that cost every time. ConnectionPool already existed for exactly this
# (persistent connections, idle reaping, keepalive) but was never wired in
# here; the only two places that referenced it (server.py's pool_stats and
# resource_pool_stats) each built their own throwaway, always-empty
# instance for reporting, not this one.
#
# 2026-10-22 correction: first deployed this wiring with max_connections=10
# (up from pool.py's own default of 3) and idle_timeout=1800 (up from 300),
# sized against the largest concurrent burst observed at the gateway level
# (6 sessions) without verifying what holding that many sustained,
# simultaneously-open CLI sessions actually costs on the device side.
# Confirmed live within the hour: one router pinned itself at its full
# memory cap continuously (hundreds of thousands of reclaim cycles across a
# 2-minute observation window) and all three logged real oom_kill events
# that had never occurred before this change -- each persistent session
# costs real, non-trivial memory on the device itself, and 10 of them held
# open for up to 30 minutes per device was enough to drive sustained memory
# pressure well past what the earlier 2.5x cap bump was sized for.
#
# Landed between the two rather than a straight revert to pool.py's own
# defaults (3 / 300s) or the original 10 / 1800s that caused the oom_kills:
# max_connections=5 (pool.py default was 3) -- modest headroom over a
# single device's typical load without coming close to the 10 that pinned
# one router at its memory cap.
# idle_timeout=600s/10min (pool.py default was 300s/5min, the original fix
# used 1800s/30min) -- still meaningfully longer than the default, so fewer
# calls land on a reaped connection than the stock 5-minute window would
# produce, without holding connections open anywhere near as long as what
# caused the sustained pressure.
#
# Neither number is verified safe the way pool.py's own defaults are --
# they're a deliberate middle ground after the 10/1800s incident, not a
# re-measured safe ceiling. Watch router memory after this deploys the same
# way the first attempt should have been watched before calling it done.
_DEFAULT_POOL_MAX_CONNECTIONS = 5
_DEFAULT_POOL_IDLE_TIMEOUT = 600.0


class DeviceManager:
    """Manages network device configurations and connections."""

    def __init__(
        self,
        config_path: str | None = None,
        pool: ConnectionPool | None = None,
    ):
        self._devices: dict[str, DeviceConfig] = {}
        self._pool = pool or ConnectionPool(
            max_connections=_DEFAULT_POOL_MAX_CONNECTIONS,
            idle_timeout=_DEFAULT_POOL_IDLE_TIMEOUT,
        )
        if config_path:
            self.load_config(config_path)

    @property
    def pool(self) -> ConnectionPool:
        """The shared connection pool backing connect() -- exposed so
        server.py's pool_stats()/resource_pool_stats() can report on the
        real pool instead of constructing their own throwaway instance."""
        return self._pool

    def load_config(self, path: str) -> None:
        """Load device configurations from a YAML file."""
        config_file = Path(path)
        if not config_file.exists():
            logger.warning("Config file not found: %s", path)
            return

        with open(config_file) as f:
            raw = yaml.safe_load(f)

        if not raw or not isinstance(raw, dict):
            logger.warning("Empty or invalid config: %s", path)
            return

        for name, cfg in raw.items():
            try:
                self._devices[name] = DeviceConfig(**cfg)
                logger.info("Loaded device: %s (%s)", name, cfg.get("host"))
            except Exception as e:
                logger.error("Failed to load device '%s': %s", name, e)

    def add_device(self, name: str, config: DeviceConfig) -> None:
        """Add a device configuration programmatically."""
        self._devices[name] = config

    def remove_device(self, name: str) -> bool:
        """Remove a device configuration."""
        return self._devices.pop(name, None) is not None

    def get_device(self, name: str) -> DeviceConfig:
        """Get a device config by name."""
        device = self._devices.get(name)
        if device is None:
            available = ", ".join(sorted(self._devices.keys())) or "(none)"
            raise ValueError(
                f"Unknown device: '{name}'. Available devices: {available}"
            )
        return device

    def list_devices(self) -> list[DeviceInfo]:
        """List all configured devices."""
        return [
            DeviceInfo(
                name=name,
                host=cfg.host,
                vendor=cfg.device_type,
                port=cfg.port,
            )
            for name, cfg in sorted(self._devices.items())
        ]

    @contextmanager
    def connect(self, device_name: str) -> Generator:
        """Context manager for a pooled device connection.

        Checks a persistent connection out of the shared ConnectionPool
        (reused across calls when idle, reconnected only when the pool has
        none available or the idle one has gone stale) instead of opening
        and tearing down a fresh SSH session on every call -- see the
        ConnectionPool wiring note above for why that mattered here.

        Usage:
            with manager.connect("router1") as conn:
                output = conn.send_command("show version")
        """
        config = self.get_device(device_name)

        connection = None
        try:
            logger.debug("Checking out connection to %s (%s)...", device_name, config.host)
            connection = self._pool.get_connection(device_name, config)
            logger.debug("Connected to %s", device_name)
            yield connection
        except NetmikoTimeoutException:
            raise ConnectionError(
                f"Connection to '{device_name}' ({config.host}) timed out after {config.timeout}s"
            )
        except NetmikoAuthenticationException:
            raise ConnectionError(
                f"Authentication failed for '{device_name}' ({config.host})"
            )
        except Exception as e:
            raise ConnectionError(
                f"Failed to connect to '{device_name}' ({config.host}): {e}"
            )
        finally:
            if connection is not None:
                # release_connection() checks liveness itself and discards
                # (rather than pools) a connection a failed command left in
                # a bad state -- safe to call unconditionally here even when
                # the block above raised.
                self._pool.release_connection(device_name, connection)

    def check_health(self, device_name: str) -> HealthStatus:
        """Check if a device is reachable and measure response time."""
        start = time.monotonic()
        try:
            with self.connect(device_name) as conn:
                conn.send_command("", read_timeout=10)
                elapsed = (time.monotonic() - start) * 1000
                return HealthStatus(
                    device=device_name,
                    reachable=True,
                    response_time_ms=round(elapsed, 2),
                )
        except Exception as e:
            elapsed = (time.monotonic() - start) * 1000
            return HealthStatus(
                device=device_name,
                reachable=False,
                response_time_ms=round(elapsed, 2),
                error=str(e),
            )
