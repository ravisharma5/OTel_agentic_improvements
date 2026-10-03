"""Tests for command allowlist enforcement.

Verifies the deny-by-default command allowlist scaffold (D-10a):
- Empty allowlist rejects all commands
- Populated allowlist accepts listed commands
- Populated allowlist rejects unlisted commands
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import yaml


def load_allowlist(allowlist_path: str | Path) -> list[str]:
    """Load the command allowlist from a YAML file.

    Returns the list of allowed command prefixes. An empty list
    means all commands are denied (deny-by-default).
    """
    path = Path(allowlist_path)
    if not path.exists():
        return []
    data = yaml.safe_load(path.read_text())
    if data is None:
        return []
    return data.get("allowed_commands", []) or []


def check_command_allowed(command: str, allowlist: list[str]) -> bool:
    """Check if a command is permitted by the allowlist.

    Returns True only if the command starts with one of the allowed
    command prefixes. When the allowlist is empty, all commands are
    denied (deny-by-default).
    """
    if not allowlist:
        return False
    cmd = command.strip().lower()
    return any(cmd.startswith(prefix.lower()) for prefix in allowlist)


class TestAllowlistDenyByDefault:
    """Test that an empty allowlist rejects all commands."""

    def test_empty_allowlist_rejects_show_command(self):
        """Empty allowlist must reject even safe 'show' commands."""
        allowlist: list[str] = []
        assert check_command_allowed("show bgp summary", allowlist) is False

    def test_empty_allowlist_rejects_ping(self):
        """Empty allowlist must reject ping commands."""
        allowlist: list[str] = []
        assert check_command_allowed("ping 10.0.0.1", allowlist) is False

    def test_empty_allowlist_rejects_config_command(self):
        """Empty allowlist must reject configuration commands."""
        allowlist: list[str] = []
        assert check_command_allowed("configure terminal", allowlist) is False

    def test_empty_allowlist_from_yaml_file(self):
        """Loading the actual scaffold file should produce an empty allowlist."""
        scaffold_path = (
            Path(__file__).parent.parent / "command_allowlist.yaml"
        )
        if scaffold_path.exists():
            allowlist = load_allowlist(scaffold_path)
            assert allowlist == []
            assert check_command_allowed("show interfaces", allowlist) is False


class TestAllowlistAcceptsListed:
    """Test that a populated allowlist accepts listed commands."""

    def test_exact_match_accepted(self):
        """Command matching an allowlist entry exactly is accepted."""
        allowlist = ["show bgp summary", "show interfaces", "ping"]
        assert check_command_allowed("show bgp summary", allowlist) is True

    def test_prefix_match_accepted(self):
        """Command starting with an allowlist prefix is accepted."""
        allowlist = ["show bgp", "ping"]
        assert check_command_allowed("show bgp neighbors", allowlist) is True

    def test_ping_with_args_accepted(self):
        """Ping with arguments accepted when 'ping' is allowlisted."""
        allowlist = ["ping"]
        assert check_command_allowed("ping 192.168.1.1", allowlist) is True

    def test_case_insensitive_match(self):
        """Allowlist matching should be case-insensitive."""
        allowlist = ["Show BGP Summary"]
        assert check_command_allowed("show bgp summary", allowlist) is True


class TestAllowlistRejectsUnlisted:
    """Test that a populated allowlist rejects unlisted commands."""

    def test_unlisted_show_command_rejected(self):
        """Show command not in allowlist is rejected."""
        allowlist = ["show bgp summary", "ping"]
        assert check_command_allowed("show routing table", allowlist) is False

    def test_config_command_rejected(self):
        """Configuration commands are always rejected by allowlist."""
        allowlist = ["show bgp summary", "show interfaces"]
        assert check_command_allowed("configure terminal", allowlist) is False

    def test_similar_but_different_command_rejected(self):
        """Command similar to but not matching allowlist entry is rejected."""
        allowlist = ["show bgp summary"]
        assert check_command_allowed("show ospf neighbors", allowlist) is False

    def test_empty_command_rejected(self):
        """Empty command string is rejected."""
        allowlist = ["show bgp summary"]
        assert check_command_allowed("", allowlist) is False


class TestAllowlistYAMLLoading:
    """Test YAML file loading for the allowlist."""

    def test_load_empty_allowlist_file(self):
        """Loading a YAML file with empty allowed_commands returns []."""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump({"allowed_commands": []}, f)
            f.flush()
            allowlist = load_allowlist(f.name)
        os.unlink(f.name)
        assert allowlist == []

    def test_load_populated_allowlist_file(self):
        """Loading a YAML file with entries returns the command list."""
        commands = ["show bgp summary", "show interfaces", "ping"]
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            yaml.dump({"allowed_commands": commands}, f)
            f.flush()
            allowlist = load_allowlist(f.name)
        os.unlink(f.name)
        assert allowlist == commands

    def test_load_nonexistent_file_returns_empty(self):
        """Loading a nonexistent file returns an empty allowlist."""
        allowlist = load_allowlist("/tmp/nonexistent_allowlist_12345.yaml")
        assert allowlist == []
