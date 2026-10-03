"""Thread-safe SSH connection pool with persistent Netmiko sessions."""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from typing import Any

from netmiko import ConnectHandler
from netmiko.base_connection import BaseConnection

from mcp_telecom.models import DeviceConfig

logger = logging.getLogger("mcp_telecom.pool")


def _netmiko_params(config: DeviceConfig) -> dict[str, Any]:
    """Build ConnectHandler kwargs from DeviceConfig."""
    params: dict[str, Any] = {
        "device_type": config.device_type.value,
        "host": config.host,
        "username": config.username,
        "password": config.password,
        "port": config.port,
        "timeout": config.timeout,
    }
    if config.secret is not None:
        params["secret"] = config.secret
    if config.session_log is not None:
        params["session_log"] = config.session_log
    return params


def _open_connection(config: DeviceConfig) -> BaseConnection:
    """Create a new Netmiko connection."""
    return ConnectHandler(**_netmiko_params(config))


def _safe_disconnect(conn: BaseConnection | None) -> None:
    if conn is None:
        return
    try:
        conn.disconnect()
    except Exception as e:
        logger.debug("disconnect ignored: %s", e)


@dataclass
class _IdleConn:
    """An idle pooled connection with last-return time (monotonic)."""

    conn: BaseConnection
    last_used: float


@dataclass
class _DeviceState:
    """Per-device pool bookkeeping."""

    idle: deque[_IdleConn] = field(default_factory=deque)
    in_use: set[BaseConnection] = field(default_factory=set)


class PooledConnection:
    """Wraps a Netmiko connection and returns it to the pool on context exit.

    ``send_command`` retries once after reconnect if the session is stale or dead.
    Other attributes are forwarded to the underlying connection.
    """

    def __init__(
        self,
        pool: ConnectionPool,
        device_name: str,
        config: DeviceConfig,
        conn: BaseConnection,
    ) -> None:
        self._pool = pool
        self._device_name = device_name
        self._config = config
        self._conn = conn

    @property
    def connection(self) -> BaseConnection:
        """The underlying Netmiko connection (may be replaced after reconnect)."""
        return self._conn

    def send_command(self, *args: Any, **kwargs: Any) -> str:
        try:
            return self._conn.send_command(*args, **kwargs)
        except Exception as first:
            logger.warning(
                "send_command failed for %s, reconnecting: %s",
                self._device_name,
                first,
            )
            self._conn = self._pool._reconnect_after_failure(
                self._device_name, self._config, self._conn
            )
            return self._conn.send_command(*args, **kwargs)

    def __getattr__(self, name: str) -> Any:
        return getattr(self._conn, name)

    def __enter__(self) -> PooledConnection:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        self._pool.release_connection(self._device_name, self._conn)


class ConnectionPool:
    """Persistent Netmiko SSH pool per device with idle reaping and keepalive."""

    def __init__(
        self,
        max_connections: int = 3,
        idle_timeout: float = 300.0,
        reaper_interval: float = 30.0,
        keepalive_interval: float | None = None,
    ) -> None:
        if max_connections < 1:
            raise ValueError("max_connections must be >= 1")
        if idle_timeout <= 0:
            raise ValueError("idle_timeout must be positive")
        self._max = max_connections
        self._idle_timeout = idle_timeout
        self._reaper_interval = reaper_interval
        self._keepalive_interval = keepalive_interval

        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._by_device: dict[str, _DeviceState] = {}
        self._closed = False

        self._reaper_stop = threading.Event()
        self._reaper = threading.Thread(
            target=self._reaper_loop,
            name="mcp-telecom-pool-reaper",
            daemon=True,
        )
        self._reaper.start()

    def _state(self, device_name: str) -> _DeviceState:
        if device_name not in self._by_device:
            self._by_device[device_name] = _DeviceState()
        return self._by_device[device_name]

    def _total_for_device(self, st: _DeviceState) -> int:
        return len(st.idle) + len(st.in_use)

    def get_connection(self, device_name: str, config: DeviceConfig) -> BaseConnection:
        """Check out a Netmiko connection from the pool (or create one)."""
        with self._cond:
            st = self._state(device_name)
            while True:
                if self._closed:
                    raise RuntimeError("ConnectionPool is closed")
                self._prune_stale_idle_locked(device_name, st)
                # Prefer most recently returned idle connection (deque pop from right).
                while st.idle:
                    entry = st.idle.pop()
                    age = time.monotonic() - entry.last_used
                    if age > self._idle_timeout:
                        _safe_disconnect(entry.conn)
                        continue
                    conn = entry.conn
                    st.in_use.add(conn)
                    return conn

                if self._total_for_device(st) < self._max:
                    try:
                        conn = _open_connection(config)
                    except Exception:
                        logger.exception("Failed to connect to %s", device_name)
                        raise
                    st.in_use.add(conn)
                    return conn

                self._cond.wait()

    def release_connection(self, device_name: str, connection: BaseConnection) -> None:
        """Return a connection to the idle pool."""
        with self._cond:
            if self._closed:
                _safe_disconnect(connection)
                return
            st = self._state(device_name)
            if connection not in st.in_use:
                logger.warning(
                    "release_connection: connection not in use for %s; disconnecting",
                    device_name,
                )
                _safe_disconnect(connection)
                return
            st.in_use.discard(connection)
            if self._is_connection_alive(connection):
                st.idle.append(_IdleConn(connection, time.monotonic()))
            else:
                _safe_disconnect(connection)
            self._cond.notify_all()

    def _reconnect_after_failure(
        self,
        device_name: str,
        config: DeviceConfig,
        dead: BaseConnection,
    ) -> BaseConnection:
        """Replace a dead connection in the in-use set; must hold lock."""
        with self._lock:
            st = self._state(device_name)
            st.in_use.discard(dead)
            _safe_disconnect(dead)
            try:
                new_conn = _open_connection(config)
            except Exception:
                self._cond.notify_all()
                raise
            st.in_use.add(new_conn)
            return new_conn

    def _is_connection_alive(self, conn: BaseConnection) -> bool:
        try:
            t = getattr(conn, "remote_conn", None)
            if t is None:
                return False
            transport = getattr(t, "transport", None)
            if transport is None or not transport.is_active():
                return False
            return True
        except Exception:
            return False

    def _prune_stale_idle_locked(self, device_name: str, st: _DeviceState) -> None:
        now = time.monotonic()
        kept: deque[_IdleConn] = deque()
        while st.idle:
            e = st.idle.popleft()
            if now - e.last_used > self._idle_timeout:
                logger.debug("Reaping idle connection for %s", device_name)
                _safe_disconnect(e.conn)
            else:
                kept.append(e)
        st.idle = kept

    def _reaper_loop(self) -> None:
        while not self._reaper_stop.wait(timeout=self._reaper_interval):
            with self._lock:
                if self._closed:
                    break
                for name, st in list(self._by_device.items()):
                    self._prune_stale_idle_locked(name, st)
                    if self._keepalive_interval is not None:
                        self._ping_idle_locked(name, st)

    def _ping_idle_locked(self, device_name: str, st: _DeviceState) -> None:
        now = time.monotonic()
        new_idle: deque[_IdleConn] = deque()
        while st.idle:
            e = st.idle.popleft()
            if now - e.last_used >= self._keepalive_interval:
                try:
                    e.conn.send_command("", read_timeout=min(10, int(self._idle_timeout)))
                    e.last_used = time.monotonic()
                except Exception as ex:
                    logger.debug("Keepalive failed for %s: %s", device_name, ex)
                    _safe_disconnect(e.conn)
                    continue
            new_idle.append(e)
        st.idle = new_idle

    def close_all(self) -> None:
        """Disconnect all pooled connections and stop the reaper."""
        self._reaper_stop.set()
        with self._lock:
            self._closed = True
            for st in self._by_device.values():
                for e in list(st.idle):
                    _safe_disconnect(e.conn)
                st.idle.clear()
                for conn in list(st.in_use):
                    _safe_disconnect(conn)
                st.in_use.clear()
            self._by_device.clear()
            self._cond.notify_all()
        self._reaper.join(timeout=self._reaper_interval + 5.0)

    def get_stats(self) -> dict[str, Any]:
        """Return pool statistics per device and totals."""
        with self._lock:
            devices: dict[str, dict[str, int]] = {}
            total = 0
            for name, st in self._by_device.items():
                active = len(st.in_use)
                idle = len(st.idle)
                t = active + idle
                total += t
                devices[name] = {
                    "active": active,
                    "idle": idle,
                    "total": t,
                }
            return {"devices": devices, "total_connections": total}

    def __enter__(self) -> ConnectionPool:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        self.close_all()

    def pooled(
        self,
        device_name: str,
        config: DeviceConfig,
    ) -> PooledConnection:
        """Check out a connection wrapped for context-manager use and safe send_command."""
        conn = self.get_connection(device_name, config)
        return PooledConnection(self, device_name, config, conn)

    @contextmanager
    def session(
        self,
        device_name: str,
        config: DeviceConfig,
    ) -> Iterator[PooledConnection]:
        """Context manager yielding a :class:`PooledConnection` (same as ``pooled``)."""
        with self.pooled(device_name, config) as wrapped:
            yield wrapped
