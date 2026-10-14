"""Data models for MCP-Telecom."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class VendorType(str, Enum):
    """Supported network equipment vendors."""

    NOKIA_SROS = "nokia_sros"
    NOKIA_SROS_TELNET = "nokia_sros_telnet"
    # Value is "nokia_srl", not "nokia_srlinux" -- this gets passed straight
    # through to Netmiko's ConnectHandler(device_type=...), whose actual
    # supported platform key for SR Linux is "nokia_srl" (confirmed live via
    # netmiko.ssh_dispatcher.CLASS_MAPPER, 2026-10-14). "nokia_srlinux" is a
    # separate namespace: that's the Containerlab "kind" string (see
    # containerlab.py's VENDOR_TO_CLAB_KIND), unrelated to Netmiko's platform
    # names -- don't conflate the two again.
    NOKIA_SRLINUX = "nokia_srl"
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
