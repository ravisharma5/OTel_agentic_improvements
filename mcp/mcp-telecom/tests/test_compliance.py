"""Tests for configuration compliance checking."""

from __future__ import annotations

import re

import pytest
from pydantic import ValidationError

from mcp_telecom.compliance import (
    DEFAULT_RULES,
    ComplianceChecker,
    ComplianceRule,
)

SAMPLE_CONFIG = """ntp server 10.0.0.1
ip ssh version 2
service password-encryption
logging buffered 8192
banner motd ^Authorized access only^
"""


class TestComplianceRule:
    def test_valid_regex_accepted(self):
        rule = ComplianceRule(
            name="t",
            description="d",
            pattern=r"\bfoo\b",
            match_type="must_contain",
            severity="info",
            remediation="r",
        )
        assert rule.pattern == r"\bfoo\b"

    def test_invalid_regex_rejected(self):
        with pytest.raises((ValidationError, re.error)):
            ComplianceRule(
                name="t",
                description="d",
                pattern=r"(unclosed",
                match_type="must_contain",
                severity="info",
                remediation="r",
            )


class TestComplianceChecker:
    def test_must_contain_pass(self):
        checker = ComplianceChecker(
            [
                ComplianceRule(
                    name="has_ntp",
                    description="NTP line",
                    pattern=r"ntp\s+server",
                    match_type="must_contain",
                    severity="warning",
                    remediation="add ntp",
                )
            ]
        )
        results = checker.check_config("r1", SAMPLE_CONFIG)
        assert len(results) == 1
        assert results[0].passed is True
        assert "ntp server" in results[0].matched_lines[0]

    def test_must_contain_fail(self):
        checker = ComplianceChecker(
            [
                ComplianceRule(
                    name="missing",
                    description="need foo",
                    pattern=r"\bFOO_UNIQUE_XYZ\b",
                    match_type="must_contain",
                    severity="critical",
                    remediation="add foo",
                )
            ]
        )
        results = checker.check_config("r1", SAMPLE_CONFIG)
        assert len(results) == 1
        assert results[0].passed is False
        assert results[0].matched_lines == []

    def test_must_not_contain_pass(self):
        checker = ComplianceChecker(
            [
                ComplianceRule(
                    name="no_telnet_transport",
                    description="no telnet on vty",
                    pattern=r"transport\s+input[^\n]*telnet",
                    match_type="must_not_contain",
                    severity="critical",
                    remediation="use ssh only",
                )
            ]
        )
        results = checker.check_config("r1", SAMPLE_CONFIG)
        assert results[0].passed is True

    def test_must_not_contain_fail(self):
        cfg = SAMPLE_CONFIG + "\nline vty 0 4\n transport input telnet\n"
        checker = ComplianceChecker(
            [
                ComplianceRule(
                    name="no_telnet_transport",
                    description="no telnet on vty",
                    pattern=r"transport\s+input[^\n]*telnet",
                    match_type="must_not_contain",
                    severity="critical",
                    remediation="use ssh only",
                )
            ]
        )
        results = checker.check_config("r1", cfg)
        assert results[0].passed is False
        assert results[0].matched_lines

    def test_vendor_rule_only_for_matching_vendor(self):
        checker = ComplianceChecker(
            [
                ComplianceRule(
                    name="ios_only",
                    description="ios marker",
                    pattern=r"CISCO_IOS_ONLY_TOKEN",
                    match_type="must_contain",
                    severity="warning",
                    vendor="cisco_ios",
                    remediation="n/a",
                )
            ]
        )
        r_ios = checker.check_config("r1", SAMPLE_CONFIG, vendor="cisco_ios")
        assert len(r_ios) == 1
        assert r_ios[0].passed is False

        r_other = checker.check_config("r1", SAMPLE_CONFIG, vendor="juniper_junos")
        assert r_other == []

        r_none = checker.check_config("r1", SAMPLE_CONFIG, vendor=None)
        assert r_none == []

    def test_default_rules_count(self):
        assert len(DEFAULT_RULES) >= 15

    def test_generate_report_format(self):
        checker = ComplianceChecker(
            [
                ComplianceRule(
                    name="a",
                    description="desc",
                    pattern=r"ntp",
                    match_type="must_contain",
                    severity="info",
                    remediation="fix",
                )
            ]
        )
        results = checker.check_config("dev1", SAMPLE_CONFIG)
        text = checker.generate_report(results)
        assert "Compliance report" in text
        assert "device(s):" in text
        assert "Score:" in text
        assert "[PASS]" in text or "[FAIL]" in text

    def test_get_score_fully_compliant(self):
        checker = ComplianceChecker(
            [
                ComplianceRule(
                    name="ok",
                    description="d",
                    pattern=r"ntp",
                    match_type="must_contain",
                    severity="warning",
                    remediation="r",
                )
            ]
        )
        results = checker.check_config("r1", SAMPLE_CONFIG)
        assert checker.get_score(results) == 1.0

    def test_get_score_non_compliant(self):
        checker = ComplianceChecker(
            [
                ComplianceRule(
                    name="bad",
                    description="d",
                    pattern=r"NEVER_MATCH_XYZ123",
                    match_type="must_contain",
                    severity="critical",
                    remediation="r",
                )
            ]
        )
        results = checker.check_config("r1", SAMPLE_CONFIG)
        assert checker.get_score(results) < 1.0

    def test_sample_config_against_defaults_score_below_one(self):
        checker = ComplianceChecker(rules=list(DEFAULT_RULES))
        results = checker.check_config("r1", SAMPLE_CONFIG)
        assert len(results) >= 15
        assert checker.get_score(results) < 1.0

    def test_load_rules_from_dict(self):
        checker = ComplianceChecker()
        checker.load_rules_from_dict(
            [
                {
                    "name": "x",
                    "description": "d",
                    "pattern": r"hello",
                    "match_type": "must_contain",
                    "severity": "info",
                    "remediation": "r",
                }
            ]
        )
        results = checker.check_config("r1", "hello world")
        assert len(results) == 1
        assert results[0].passed is True
