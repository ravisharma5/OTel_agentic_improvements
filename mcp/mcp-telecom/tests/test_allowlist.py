"""Tests for command allowlist enforcement in production safety.py.

Verifies the deny-by-default command allowlist (CR-01):
- Empty allowlist rejects all commands (via validate_command)
- Populated allowlist accepts listed commands (via validate_command)
- Populated allowlist rejects unlisted commands (via validate_command)
- _load_allowlist() reads YAML files correctly
"""

from __future__ import annotations

import yaml

from mcp_telecom.safety import _load_allowlist, validate_command
from mcp_telecom import safety


class TestAllowlistDenyByDefault:
    """Test that an empty allowlist rejects all commands."""

    def test_empty_allowlist_rejects_show_command(self, monkeypatch):
        """Empty allowlist must reject even safe 'show' commands via validate_command."""
        monkeypatch.setenv("MCP_TELECOM_ALLOWLIST_FILE", "/tmp/nonexistent_allowlist_99999.yaml")
        safety._allowlist_cache = None
        result = validate_command("show bgp summary")
        assert result is not None
        assert "allowlist" in result.lower()

    def test_empty_allowlist_rejects_ping(self, monkeypatch):
        """Empty allowlist must reject ping commands via validate_command."""
        monkeypatch.setenv("MCP_TELECOM_ALLOWLIST_FILE", "/tmp/nonexistent_allowlist_99999.yaml")
        safety._allowlist_cache = None
        result = validate_command("ping 10.0.0.1")
        assert result is not None
        assert "allowlist" in result.lower()

    def test_empty_allowlist_from_yaml_file(self, tmp_path, monkeypatch):
        """Loading the actual scaffold (empty allowed_commands) denies commands."""
        allowlist_file = tmp_path / "allowlist.yaml"
        allowlist_file.write_text(yaml.dump({"allowed_commands": []}))
        monkeypatch.setenv("MCP_TELECOM_ALLOWLIST_FILE", str(allowlist_file))
        safety._allowlist_cache = None
        result = validate_command("show interfaces")
        assert result is not None
        assert "allowlist" in result.lower()


class TestAllowlistAcceptsListed:
    """Test that a populated allowlist accepts listed commands."""

    def test_prefix_match_accepted(self, tmp_path, monkeypatch):
        """Command starting with an allowlist prefix is accepted."""
        allowlist_file = tmp_path / "allowlist.yaml"
        allowlist_file.write_text(yaml.dump({"allowed_commands": ["show bgp", "ping"]}))
        monkeypatch.setenv("MCP_TELECOM_ALLOWLIST_FILE", str(allowlist_file))
        safety._allowlist_cache = None
        assert validate_command("show bgp summary") is None

    def test_ping_with_args_accepted(self, tmp_path, monkeypatch):
        """Ping with arguments accepted when 'ping' is allowlisted."""
        allowlist_file = tmp_path / "allowlist.yaml"
        allowlist_file.write_text(yaml.dump({"allowed_commands": ["ping", "show"]}))
        monkeypatch.setenv("MCP_TELECOM_ALLOWLIST_FILE", str(allowlist_file))
        safety._allowlist_cache = None
        assert validate_command("ping 192.168.1.1") is None

    def test_case_insensitive_match(self, tmp_path, monkeypatch):
        """Allowlist matching should be case-insensitive."""
        allowlist_file = tmp_path / "allowlist.yaml"
        allowlist_file.write_text(yaml.dump({"allowed_commands": ["Show BGP"]}))
        monkeypatch.setenv("MCP_TELECOM_ALLOWLIST_FILE", str(allowlist_file))
        safety._allowlist_cache = None
        assert validate_command("show bgp summary") is None


class TestAllowlistRejectsUnlisted:
    """Test that a populated allowlist rejects unlisted commands."""

    def test_unlisted_show_command_rejected(self, tmp_path, monkeypatch):
        """Show command not in allowlist is rejected."""
        allowlist_file = tmp_path / "allowlist.yaml"
        allowlist_file.write_text(yaml.dump({"allowed_commands": ["show bgp", "ping"]}))
        monkeypatch.setenv("MCP_TELECOM_ALLOWLIST_FILE", str(allowlist_file))
        safety._allowlist_cache = None
        result = validate_command("show ospf neighbors")
        assert result is not None
        assert "allowlist" in result.lower()

    def test_config_command_still_blocked_by_safety(self, tmp_path, monkeypatch):
        """Configuration commands blocked by safety check before allowlist."""
        allowlist_file = tmp_path / "allowlist.yaml"
        allowlist_file.write_text(yaml.dump({"allowed_commands": ["show bgp", "ping"]}))
        monkeypatch.setenv("MCP_TELECOM_ALLOWLIST_FILE", str(allowlist_file))
        safety._allowlist_cache = None
        result = validate_command("configure terminal")
        assert result is not None
        assert "blocked" in result.lower()

    def test_empty_command_still_returns_empty_error(self):
        """Empty command string returns 'Empty command' error (before allowlist)."""
        result = validate_command("")
        assert result is not None
        assert "Empty command" in result


class TestAllowlistYAMLLoading:
    """Test YAML file loading for the allowlist via _load_allowlist."""

    def test_load_empty_allowlist_file(self, tmp_path, monkeypatch):
        """Loading a YAML file with empty allowed_commands returns []."""
        allowlist_file = tmp_path / "allowlist.yaml"
        allowlist_file.write_text(yaml.dump({"allowed_commands": []}))
        monkeypatch.setenv("MCP_TELECOM_ALLOWLIST_FILE", str(allowlist_file))
        safety._allowlist_cache = None
        allowlist = _load_allowlist()
        assert allowlist == []

    def test_load_populated_allowlist_file(self, tmp_path, monkeypatch):
        """Loading a YAML file with entries returns the command list."""
        commands = ["show bgp summary", "show interfaces", "ping"]
        allowlist_file = tmp_path / "allowlist.yaml"
        allowlist_file.write_text(yaml.dump({"allowed_commands": commands}))
        monkeypatch.setenv("MCP_TELECOM_ALLOWLIST_FILE", str(allowlist_file))
        safety._allowlist_cache = None
        allowlist = _load_allowlist()
        assert allowlist == commands

    def test_load_nonexistent_file_returns_empty(self, monkeypatch):
        """Loading a nonexistent file returns an empty allowlist."""
        monkeypatch.setenv("MCP_TELECOM_ALLOWLIST_FILE", "/tmp/nonexistent_allowlist_12345.yaml")
        safety._allowlist_cache = None
        allowlist = _load_allowlist()
        assert allowlist == []
