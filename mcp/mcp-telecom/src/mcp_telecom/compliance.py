"""Configuration compliance checking against regex rules."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator

MatchType = Literal["must_contain", "must_not_contain"]
Severity = Literal["critical", "warning", "info"]


class ComplianceRule(BaseModel):
    name: str
    description: str
    pattern: str
    match_type: MatchType
    severity: Severity
    vendor: str | None = None
    remediation: str

    @field_validator("pattern")
    @classmethod
    def pattern_must_compile(cls, v: str) -> str:
        re.compile(v)
        return v


class ComplianceResult(BaseModel):
    rule: ComplianceRule
    passed: bool
    matched_lines: list[str] = Field(default_factory=list)
    device: str


def _normalize_vendor(v: str | None) -> str | None:
    if v is None:
        return None
    return v.strip().lower()


def _line_matches(pattern: re.Pattern[str], line: str) -> bool:
    return bool(pattern.search(line))


class ComplianceChecker:
    def __init__(self, rules: list[ComplianceRule] | None = None) -> None:
        self._rules: list[ComplianceRule] = list(rules) if rules else []

    def load_rules_from_yaml(self, path: str | Path) -> None:
        raw = Path(path).read_text(encoding="utf-8")
        data = yaml.safe_load(raw)
        if data is None:
            return
        if isinstance(data, dict) and "rules" in data:
            items = data["rules"]
        elif isinstance(data, list):
            items = data
        else:
            raise ValueError("YAML must be a list of rules or a dict with a 'rules' key")
        self.load_rules_from_dict(items)

    def load_rules_from_dict(self, rules_list: list[dict]) -> None:
        for item in rules_list:
            self._rules.append(ComplianceRule.model_validate(item))

    def add_rule(self, rule: ComplianceRule) -> None:
        self._rules.append(rule)

    def check_config(
        self,
        device: str,
        config_text: str,
        vendor: str | None = None,
    ) -> list[ComplianceResult]:
        nv = _normalize_vendor(vendor)
        lines = config_text.splitlines()
        results: list[ComplianceResult] = []

        for rule in self._rules:
            if rule.vendor is not None and nv is not None:
                if _normalize_vendor(rule.vendor) != nv:
                    continue
            elif rule.vendor is not None and nv is None:
                continue

            compiled = re.compile(rule.pattern)
            matched: list[str] = []
            for line in lines:
                if _line_matches(compiled, line):
                    matched.append(line.rstrip("\r"))

            if rule.match_type == "must_contain":
                passed = len(matched) > 0
                matched_lines = matched if passed else []
            else:
                passed = len(matched) == 0
                matched_lines = matched if not passed else []

            results.append(
                ComplianceResult(
                    rule=rule,
                    passed=passed,
                    matched_lines=matched_lines,
                    device=device,
                )
            )

        return results

    def generate_report(self, results: list[ComplianceResult]) -> str:
        if not results:
            return "No compliance results.\n"

        lines_out: list[str] = []
        devices = sorted({r.device for r in results})
        lines_out.append(f"Compliance report — device(s): {', '.join(devices)}")
        lines_out.append(f"Score: {self.get_score(results):.2%}")
        lines_out.append("")

        for r in results:
            status = "PASS" if r.passed else "FAIL"
            lines_out.append(f"[{status}] [{r.rule.severity.upper()}] {r.rule.name}")
            lines_out.append(f"  Device: {r.device}")
            lines_out.append(f"  {r.rule.description}")
            if not r.passed:
                lines_out.append(f"  Remediation: {r.rule.remediation}")
            if r.matched_lines:
                lines_out.append("  Matched lines:")
                for ml in r.matched_lines[:20]:
                    lines_out.append(f"    {ml}")
                if len(r.matched_lines) > 20:
                    lines_out.append(f"    ... ({len(r.matched_lines) - 20} more)")
            lines_out.append("")

        return "\n".join(lines_out).rstrip() + "\n"

    def get_score(self, results: list[ComplianceResult]) -> float:
        if not results:
            return 1.0

        weights = {"critical": 4.0, "warning": 2.0, "info": 1.0}
        earned = 0.0
        total = 0.0
        for r in results:
            w = weights[r.rule.severity]
            total += w
            if r.passed:
                earned += w
        return earned / total if total > 0 else 1.0


DEFAULT_RULES: list[ComplianceRule] = [
    ComplianceRule(
        name="ntp_configured",
        description="NTP (time synchronization) should be configured.",
        pattern=r"(?i)\bntp\s+(server|peer|master)|clock\s+ntp|ntp\s+association",
        match_type="must_contain",
        severity="critical",
        vendor=None,
        remediation="Configure NTP servers (e.g. ntp server <address> or vendor equivalent).",
    ),
    ComplianceRule(
        name="ssh_enabled",
        description="SSH access should be enabled for remote management.",
        pattern=r"(?i)\bip\s+ssh\b|\bssh\s+server\b|\bssh\s+version\b|\bsystem\s+ssh-server\b",
        match_type="must_contain",
        severity="critical",
        vendor=None,
        remediation="Enable SSH (ip ssh version 2, ssh server, or platform SSH service).",
    ),
    ComplianceRule(
        name="telnet_disabled_on_vty",
        description="Telnet should not be allowed on VTY/management lines.",
        pattern=r"(?i)transport\s+input[^\n]*\btelnet\b|transport\s+input\s+all",
        match_type="must_not_contain",
        severity="critical",
        vendor=None,
        remediation="Use 'transport input ssh' or restrict to SSH only on line vty.",
    ),
    ComplianceRule(
        name="no_snmp_default_communities",
        description='SNMP communities "public" or "private" must not be used.',
        pattern=r"(?i)community\s+[\"']?(public|private)[\"']?\b",
        match_type="must_not_contain",
        severity="critical",
        vendor=None,
        remediation="Remove default communities; use SNMPv3 or strong unique community strings.",
    ),
    ComplianceRule(
        name="logging_configured",
        description="Syslog or remote logging should be configured.",
        pattern=r"(?i)\blogging\s+|\bsyslog\b|\blog\s+host\b|\blog-host\b",
        match_type="must_contain",
        severity="warning",
        vendor=None,
        remediation="Configure logging to a syslog server or centralized log host.",
    ),
    ComplianceRule(
        name="aaa_or_tacacs_or_radius",
        description="AAA, TACACS+, or RADIUS should be configured for authentication.",
        pattern=r"(?i)\baaa\s+new-model\b|\baaa\s+authentication\b|\btacacs|tacplus|radius-server|\bradius\s+server\b",
        match_type="must_contain",
        severity="warning",
        vendor=None,
        remediation="Enable AAA new-model and TACACS+/RADIUS for login authentication.",
    ),
    ComplianceRule(
        name="banner_configured",
        description="A login or MOTD banner should be configured.",
        pattern=r"(?i)\bbanner\s+(login|motd|exec)\b|\bmessage-of-the-day\b",
        match_type="must_contain",
        severity="info",
        vendor=None,
        remediation="Add a legal/authorized-use banner (banner login / motd).",
    ),
    ComplianceRule(
        name="password_encryption",
        description="Password encryption in configuration should be enabled.",
        pattern=r"(?i)\bservice\s+password-encryption\b|\bpassword-hash\b|\bencrypted-password\b",
        match_type="must_contain",
        severity="critical",
        vendor=None,
        remediation=(
            "Enable service password-encryption or use "
            "hashed/encrypted password statements."
        ),
    ),
    ComplianceRule(
        name="no_obvious_default_passwords",
        description="Obvious default or trivial passwords should not appear in config.",
        pattern=r"(?i)\bpassword\s+(0\s+)?5?\s*cisco\b|\bpassword\s+(0\s+)?5?\s*admin\b|\bsecret\s+0\s+cisco\b",
        match_type="must_not_contain",
        severity="critical",
        vendor=None,
        remediation=(
            "Replace default passwords with strong secrets "
            "and store as type 5/8/9 or hashed."
        ),
    ),
    ComplianceRule(
        name="spanning_tree_enabled",
        description="Spanning Tree should be enabled on switches (loop prevention).",
        pattern=r"(?i)\bspanning-tree\s+|\bstp\s+mode\b|\bspanning_tree\b",
        match_type="must_contain",
        severity="info",
        vendor=None,
        remediation="Enable STP/RSTP/MSTP appropriate to the L2 topology.",
    ),
    ComplianceRule(
        name="ospf_authentication",
        description=(
            "OSPF authentication (MD5 or key chain) should "
            "be configured when OSPF is used."
        ),
        pattern=r"(?i)\b(ip\s+ospf\s+message-digest-key|ospf\s+message-digest|message-digest-key|authentication-key|authentication\s+message-digest)\b",
        match_type="must_contain",
        severity="warning",
        vendor=None,
        remediation=(
            "Configure per-interface or area OSPF auth "
            "(message-digest-key or equivalent)."
        ),
    ),
    ComplianceRule(
        name="bgp_neighbor_password",
        description="BGP peers should use TCP MD5 or neighbor password where applicable.",
        pattern=r"(?i)\bneighbor\s+\S+\s+password\b|\bpeer\s+\S+\s+authentication-key\b|\btcp-md5\b",
        match_type="must_contain",
        severity="warning",
        vendor=None,
        remediation="Add neighbor password / authentication-key for BGP sessions.",
    ),
    ComplianceRule(
        name="console_exec_timeout",
        description="Console/session exec timeout should be set.",
        pattern=r"(?i)\bexec-timeout\b|\bidle-timeout\b|\babsolute-timeout\b",
        match_type="must_contain",
        severity="warning",
        vendor=None,
        remediation="Set exec-timeout on console and VTY lines (e.g. exec-timeout 5 0).",
    ),
    ComplianceRule(
        name="vty_access_class",
        description="VTY lines should restrict access with an ACL or access-class.",
        pattern=r"(?i)\b(access-class|ipv4\s+access-class)\s+(in|ingress)\b",
        match_type="must_contain",
        severity="warning",
        vendor=None,
        remediation="Apply access-class inbound on line vty to limit source addresses.",
    ),
    ComplianceRule(
        name="ssh_version_2",
        description="SSH protocol version 2 should be preferred.",
        pattern=r"(?i)\bip\s+ssh\s+version\s+2\b|\bssh\s+version\s+2\b|\bprotocol-version\s+v2\b",
        match_type="must_contain",
        severity="info",
        vendor=None,
        remediation="Set SSH to version 2 only (ip ssh version 2).",
    ),
    ComplianceRule(
        name="dns_name_servers",
        description="DNS name servers should be configured for resolution.",
        pattern=r"(?i)\bip\s+name-server\b|\bname-server\b|\bdomain-name-server\b",
        match_type="must_contain",
        severity="info",
        vendor=None,
        remediation="Configure ip name-server or equivalent DNS resolvers.",
    ),
    ComplianceRule(
        name="no_ip_http_server",
        description="Insecure HTTP management server should be disabled.",
        pattern=r"(?i)^\s*ip\s+http\s+server\s*$",
        match_type="must_not_contain",
        severity="warning",
        vendor="cisco_ios",
        remediation="Use 'no ip http server' or enable only HTTPS with strong controls.",
    ),
    ComplianceRule(
        name="no_ip_http_server_xr",
        description="HTTP server on the device should not be left enabled without justification.",
        pattern=r"(?i)^\s*http\s+server\s*$",
        match_type="must_not_contain",
        severity="warning",
        vendor="cisco_xr",
        remediation="Disable HTTP server or restrict to HTTPS/hardened management plane.",
    ),
    ComplianceRule(
        name="configuration_archive",
        description="Configuration change logging or archive should be considered.",
        pattern=r"(?i)\barchive\b|\bconfiguration\s+change\b|\bcommit\s+scripts\b",
        match_type="must_contain",
        severity="info",
        vendor=None,
        remediation="Enable configuration archive or commit history per vendor best practice.",
    ),
    ComplianceRule(
        name="no_weak_snmp_v2c_default",
        description="SNMP should not use unrestricted ro/rw with v2c without ACL.",
        pattern=r"(?i)snmp-server\s+community\s+\S+\s+RO\s*$|snmp-server\s+community\s+\S+\s+RW\s*$",
        match_type="must_not_contain",
        severity="info",
        vendor=None,
        remediation="Bind SNMP communities to ACLs or migrate to SNMPv3.",
    ),
]
