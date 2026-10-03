from __future__ import annotations

import asyncio
from collections.abc import Iterable, Mapping
from typing import Any

try:
    from pysnmp.entity.engine import SnmpEngine
    from pysnmp.hlapi.v3arch.asyncio import (
        CommunityData,
        ContextData,
        ObjectIdentity,
        ObjectType,
        Udp6TransportTarget,
        UdpTransportTarget,
        UsmUserData,
        bulk_cmd,
        get_cmd,
        walk_cmd,
    )
    from pysnmp.hlapi.v3arch.asyncio.auth import (
        USM_AUTH_HMAC96_MD5,
        USM_AUTH_HMAC96_SHA,
        USM_AUTH_NONE,
        USM_PRIV_CBC56_DES,
        USM_PRIV_CFB128_AES,
        USM_PRIV_CFB192_AES,
        USM_PRIV_CFB256_AES,
        USM_PRIV_NONE,
    )

    PYSNMP_AVAILABLE = True
except ImportError:  # pragma: no cover - optional dependency
    PYSNMP_AVAILABLE = False
    SnmpEngine = CommunityData = ContextData = ObjectIdentity = ObjectType = None  # type: ignore
    UdpTransportTarget = Udp6TransportTarget = UsmUserData = None  # type: ignore
    get_cmd = bulk_cmd = walk_cmd = None  # type: ignore
    USM_AUTH_HMAC96_MD5 = USM_AUTH_HMAC96_SHA = USM_AUTH_NONE = None  # type: ignore
    USM_PRIV_CBC56_DES = USM_PRIV_CFB128_AES = USM_PRIV_NONE = None  # type: ignore
    USM_PRIV_CFB192_AES = USM_PRIV_CFB256_AES = None  # type: ignore


SYS_DESCR = "1.3.6.1.2.1.1.1.0"
SYS_UPTIME = "1.3.6.1.2.1.1.3.0"
SYS_CONTACT = "1.3.6.1.2.1.1.4.0"
SYS_NAME = "1.3.6.1.2.1.1.5.0"
SYS_LOCATION = "1.3.6.1.2.1.1.6.0"

IF_DESCR = "1.3.6.1.2.1.2.2.1.2"
IF_OPER_STATUS = "1.3.6.1.2.1.2.2.1.8"
IF_ADMIN_STATUS = "1.3.6.1.2.1.2.2.1.7"
IF_IN_OCTETS = "1.3.6.1.2.1.2.2.1.10"
IF_OUT_OCTETS = "1.3.6.1.2.1.2.2.1.16"
IF_SPEED = "1.3.6.1.2.1.2.2.1.5"
IF_IN_ERRORS = "1.3.6.1.2.1.2.2.1.14"
IF_OUT_ERRORS = "1.3.6.1.2.1.2.2.1.20"

BGP_PEER_STATE = "1.3.6.1.2.1.15.3.1.2"
BGP_PEER_REMOTE_AS = "1.3.6.1.2.1.15.3.1.9"

ENT_PHYSICAL_NAME = "1.3.6.1.2.1.47.1.1.1.1.7"
ENT_PHYSICAL_DESCR = "1.3.6.1.2.1.47.1.1.1.1.2"

HR_PROCESSOR_LOAD = "1.3.6.1.2.1.25.3.3.1.2"
HR_STORAGE_USED = "1.3.6.1.2.1.25.2.3.1.6"


class SnmpError(RuntimeError):
    pass


def _require_pysnmp() -> None:
    if not PYSNMP_AVAILABLE:
        raise RuntimeError("pysnmp is not installed; add the `snmp` extra or `pip install pysnmp`.")


def _auth_proto(name: str | None) -> Any:
    if not name or name.lower() in ("none", "noauth"):
        return USM_AUTH_NONE
    key = name.lower().replace("-", "")
    if key in ("md5", "hmacmd5"):
        return USM_AUTH_HMAC96_MD5
    if key in ("sha", "sha1", "hmacsha"):
        return USM_AUTH_HMAC96_SHA
    raise ValueError(f"unsupported SNMPv3 auth protocol: {name!r}")


def _priv_proto(name: str | None) -> Any:
    if not name or name.lower() in ("none", "nopriv"):
        return USM_PRIV_NONE
    key = name.lower().replace("-", "")
    if key == "des":
        return USM_PRIV_CBC56_DES
    if key in ("aes", "aes128"):
        return USM_PRIV_CFB128_AES
    if key == "aes192":
        return USM_PRIV_CFB192_AES
    if key == "aes256":
        return USM_PRIV_CFB256_AES
    raise ValueError(f"unsupported SNMPv3 privacy protocol: {name!r}")


def _varbind_pair(vb: Any) -> tuple[str, str]:
    oid = vb[0].prettyPrint()
    val = vb[1].prettyPrint() if len(vb) > 1 else ""
    return oid, val


def _check_pdu(
    error_indication: Any,
    error_status: Any,
    error_index: Any,
    *,
    op: str,
) -> None:
    if error_indication:
        raise SnmpError(f"{op}: {error_indication}")
    if error_status and int(error_status) != 0:
        idx = int(error_index) if error_index is not None else 0
        raise SnmpError(f"{op}: SNMP errorStatus={error_status!r} index={idx}")


_DEVICE_MIB_INDEX: dict[str, list[str]] = {
    "cisco": [
        "SNMPv2-MIB",
        "IF-MIB",
        "CISCO-ENTITY-VENDORTYPE-OID-MIB",
        "ENTITY-MIB",
        "BGP4-MIB",
        "CISCO-PROCESS-MIB",
        "HOST-RESOURCES-MIB",
    ],
    "cisco_ios": [
        "SNMPv2-MIB",
        "IF-MIB",
        "ENTITY-MIB",
        "BGP4-MIB",
        "HOST-RESOURCES-MIB",
    ],
    "cisco_xr": [
        "SNMPv2-MIB",
        "IF-MIB",
        "ENTITY-MIB",
        "BGP4-MIB",
        "CISCO-ENTITY-SENSOR-MIB",
        "HOST-RESOURCES-MIB",
    ],
    "juniper": ["SNMPv2-MIB", "IF-MIB", "ENTITY-MIB", "BGP4-MIB", "JUNIPER-MIB"],
    "juniper_junos": ["SNMPv2-MIB", "IF-MIB", "ENTITY-MIB", "BGP4-MIB", "JUNIPER-MIB"],
    "nokia": ["SNMPv2-MIB", "IF-MIB", "ENTITY-MIB", "BGP4-MIB", "TIMETRA-PORT-MIB"],
    "nokia_sros": ["SNMPv2-MIB", "IF-MIB", "ENTITY-MIB", "BGP4-MIB", "TIMETRA-PORT-MIB"],
    "arista": ["SNMPv2-MIB", "IF-MIB", "ENTITY-MIB", "BGP4-MIB", "HOST-RESOURCES-MIB"],
    "arista_eos": ["SNMPv2-MIB", "IF-MIB", "ENTITY-MIB", "BGP4-MIB", "HOST-RESOURCES-MIB"],
    "huawei": ["SNMPv2-MIB", "IF-MIB", "ENTITY-MIB", "BGP4-MIB", "HUAWEI-ENTITY-EXTENT-MIB"],
    "generic": ["SNMPv2-MIB", "IF-MIB", "ENTITY-MIB", "BGP4-MIB", "HOST-RESOURCES-MIB"],
}


def get_device_mibs(device_type: str) -> list[str]:
    key = device_type.strip().lower().replace(" ", "_").replace("-", "_")
    if key in _DEVICE_MIB_INDEX:
        return list(_DEVICE_MIB_INDEX[key])
    for name in sorted(_DEVICE_MIB_INDEX.keys(), key=len, reverse=True):
        if name != "generic" and key.startswith(name):
            return list(_DEVICE_MIB_INDEX[name])
    if "cisco" in key or "ios" in key or "xr" in key or "nxos" in key:
        return list(_DEVICE_MIB_INDEX["cisco_ios"])
    if "juniper" in key or "junos" in key:
        return list(_DEVICE_MIB_INDEX["juniper_junos"])
    if "nokia" in key or "sros" in key or "timos" in key:
        return list(_DEVICE_MIB_INDEX["nokia_sros"])
    if "arista" in key or "eos" in key:
        return list(_DEVICE_MIB_INDEX["arista_eos"])
    if "huawei" in key:
        return list(_DEVICE_MIB_INDEX["huawei"])
    return list(_DEVICE_MIB_INDEX["generic"])


def format_snmp_results(
    data: Iterable[tuple[str, str] | Mapping[str, Any]],
) -> str:
    lines: list[str] = []
    for row in data:
        if isinstance(row, Mapping):
            oid = str(row.get("oid", ""))
            val = str(row.get("value", ""))
        elif isinstance(row, tuple) and len(row) >= 2:
            oid, val = str(row[0]), str(row[1])
        else:
            oid, val = str(row), ""
        lines.append(f"{oid} = {val}")
    return "\n".join(lines)


class SnmpPoller:
    def __init__(
        self,
        host: str,
        port: int = 161,
        *,
        version: str = "2c",
        community: str | None = None,
        v3_user: str | None = None,
        v3_auth_key: str | None = None,
        v3_priv_key: str | None = None,
        v3_auth_protocol: str | None = None,
        v3_priv_protocol: str | None = None,
        timeout: float = 5.0,
        retries: int = 3,
    ) -> None:
        _require_pysnmp()
        ver = version.lower().replace("-", "")
        if ver in ("2c", "v2", "v2c", "snmpv2c"):
            if not community:
                raise ValueError("SNMPv2c requires community")
            self._auth: Any = CommunityData(community)
        elif ver in ("3", "v3", "snmpv3"):
            if not v3_user:
                raise ValueError("SNMPv3 requires v3_user")
            ap = _auth_proto(v3_auth_protocol)
            pp = _priv_proto(v3_priv_protocol)
            if v3_auth_key and ap is USM_AUTH_NONE:
                ap = USM_AUTH_HMAC96_MD5
            if v3_priv_key and pp is USM_PRIV_NONE:
                pp = USM_PRIV_CBC56_DES
            kw: dict[str, Any] = {}
            if v3_auth_key:
                kw["authKey"] = v3_auth_key
                kw["authProtocol"] = ap
            if v3_priv_key:
                kw["privKey"] = v3_priv_key
                kw["privProtocol"] = pp
            self._auth = UsmUserData(v3_user, **kw)
        else:
            raise ValueError(f"unsupported SNMP version: {version!r} (use '2c' or '3')")

        self._host = host
        self._port = port
        self._timeout = max(1, int(round(timeout)))
        self._retries = retries
        self._engine = SnmpEngine()

    def close(self) -> None:
        td = getattr(self._engine, "transport_dispatcher", None)
        if td is not None and hasattr(td, "close_dispatcher"):
            td.close_dispatcher()

    def __enter__(self) -> SnmpPoller:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    async def _transport(self) -> Any:
        target = (self._host, self._port)
        if ":" in self._host:
            return await Udp6TransportTarget.create(target, self._timeout, self._retries)
        return await UdpTransportTarget.create(target, self._timeout, self._retries)

    def _run(self, coro: Any) -> Any:
        return asyncio.run(coro)

    def get(self, oids: list[str]) -> list[tuple[str, str]]:
        if not oids:
            return []

        async def _go() -> list[tuple[str, str]]:
            transport = await self._transport()
            binds = [ObjectType(ObjectIdentity(oid)) for oid in oids]
            err_i, err_s, err_x, var_binds = await get_cmd(
                self._engine,
                self._auth,
                transport,
                ContextData(),
                *binds,
                lookupMib=False,
            )
            _check_pdu(err_i, err_s, err_x, op="GET")
            return [_varbind_pair(vb) for vb in var_binds]

        return self._run(_go())

    def walk(
        self,
        base_oid: str,
        *,
        max_rows: int = 0,
        max_calls: int = 0,
    ) -> list[tuple[str, str]]:
        async def _go() -> list[tuple[str, str]]:
            transport = await self._transport()
            out: list[tuple[str, str]] = []
            async for err_i, err_s, err_x, var_binds in walk_cmd(
                self._engine,
                self._auth,
                transport,
                ContextData(),
                ObjectType(ObjectIdentity(base_oid)),
                lexicographicMode=False,
                lookupMib=False,
                maxRows=max_rows,
                maxCalls=max_calls,
            ):
                _check_pdu(err_i, err_s, err_x, op="WALK")
                for vb in var_binds:
                    out.append(_varbind_pair(vb))
            return out

        return self._run(_go())

    def bulk_get(
        self,
        oids: list[str],
        *,
        non_repeaters: int = 0,
        max_repetitions: int = 25,
    ) -> list[tuple[str, str]]:
        if not oids:
            return []

        async def _go() -> list[tuple[str, str]]:
            transport = await self._transport()
            binds = [ObjectType(ObjectIdentity(oid)) for oid in oids]
            err_i, err_s, err_x, var_binds = await bulk_cmd(
                self._engine,
                self._auth,
                transport,
                ContextData(),
                non_repeaters,
                max_repetitions,
                *binds,
                lookupMib=False,
            )
            _check_pdu(err_i, err_s, err_x, op="BULK_GET")
            return [_varbind_pair(vb) for vb in var_binds]

        return self._run(_go())
