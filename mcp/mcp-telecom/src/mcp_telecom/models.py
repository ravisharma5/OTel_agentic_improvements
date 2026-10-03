"""Data models for MCP-Telecom."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class VendorType(str, Enum):
    """Supported network equipment vendors."""

    NOKIA_SROS = "nokia_sros"
    NOKIA_SROS_TELNET = "nokia_sros_telnet"
    CISCO_IOS = "cisco_ios"
    CISCO_IOSXR = "cisco_xr"
    CISCO_NXOS = "cisco_nxos"
    JUNIPER_JUNOS = "juniper_junos"
    ARISTA_EOS = "arista_eos"


class DeviceConfig(BaseModel):
    """Configuration for a network device."""

    device_type: VendorType
    host: str
    username: str
    password: str = Field(repr=False)
    port: int = 22
    secret: str | None = Field(default=None, repr=False)
    timeout: int = 30
    session_log: str | None = None


class CommandResult(BaseModel):
    """Result of a command execution on a device."""

    device: str
    command: str
    output: str
    vendor: VendorType
    success: bool = True
    error: str | None = None


class DeviceInfo(BaseModel):
    """Summary info about a configured device."""

    name: str
    host: str
    vendor: VendorType
    port: int


class HealthStatus(BaseModel):
    """Health check result for a device."""

    device: str
    reachable: bool
    response_time_ms: float | None = None
    error: str | None = None
