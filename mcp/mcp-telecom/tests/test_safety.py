"""Tests for command safety validation."""

import pytest

from mcp_telecom.safety import is_safe_command, validate_command


class TestIsSafeCommand:
    """Test the command safety checker."""

    @pytest.mark.parametrize(
        "command",
        [
            "show version",
            "show ip interface brief",
            "show router bgp summary",
            "show interfaces terse",
            "show running-config",
            "show log messages | last 50",
            "display version",
            "ping 10.0.0.1",
            "traceroute 10.0.0.1",
            "show ip route 10.0.0.0/24",
            "  show version  ",
            "SHOW VERSION",
        ],
    )
    def test_safe_commands_allowed(self, command: str):
        assert is_safe_command(command) is True

    @pytest.mark.parametrize(
        "command",
        [
            "configure terminal",
            "config t",
            "edit",
            "set interfaces ge-0/0/0 disable",
            "delete interfaces ge-0/0/0",
            "commit",
            "rollback 1",
            "write memory",
            "copy running-config startup-config",
            "reload",
            "reboot",
            "shutdown",
            "admin save",
            "admin reboot",
            "clear counters",
            "reset bgp all",
            "erase startup-config",
            "debug ip bgp",
            "no shutdown",
            "tools dump",
            "format disk0:",
        ],
    )
    def test_dangerous_commands_blocked(self, command: str):
        assert is_safe_command(command) is False

    def test_empty_command_blocked(self):
        assert is_safe_command("") is False

    def test_random_command_blocked(self):
        assert is_safe_command("rm -rf /") is False


class TestValidateCommand:
    def test_safe_command_returns_none(self):
        assert validate_command("show version") is None

    def test_empty_command_returns_error(self):
        result = validate_command("")
        assert result is not None
        assert "Empty command" in result

    def test_dangerous_command_returns_error(self):
        result = validate_command("configure terminal")
        assert result is not None
        assert "blocked" in result.lower()
