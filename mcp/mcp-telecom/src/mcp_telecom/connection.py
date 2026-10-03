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
from netmiko import ConnectHandler, NetmikoAuthenticationException, NetmikoTimeoutException

from mcp_telecom.models import DeviceConfig, DeviceInfo, HealthStatus

logger = logging.getLogger("mcp_telecom.connection")


class DeviceManager:
    """Manages network device configurations and connections."""

    def __init__(self, config_path: str | None = None):
        self._devices: dict[str, DeviceConfig] = {}
        if config_path:
            self.load_config(config_path)

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
        """Context manager for device connections with proper cleanup.

        Usage:
            with manager.connect("router1") as conn:
                output = conn.send_command("show version")
        """
        config = self.get_device(device_name)
        conn_params = {
            "device_type": config.device_type.value,
            "host": config.host,
            "username": config.username,
            "password": config.password,
            "port": config.port,
            "timeout": config.timeout,
        }
        if config.secret:
            conn_params["secret"] = config.secret
        if config.session_log:
            conn_params["session_log"] = config.session_log

        connection = None
        try:
            logger.debug("Connecting to %s (%s)...", device_name, config.host)
            connection = ConnectHandler(**conn_params)
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
            if connection:
                try:
                    connection.disconnect()
                    logger.debug("Disconnected from %s", device_name)
                except Exception:
                    pass

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
