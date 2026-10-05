"""Tests for interface argument sanitization (CR-02).

Verifies show_interface_detail rejects interface names containing
shell metacharacters while accepting valid interface naming patterns.
"""

from __future__ import annotations

import re
from unittest.mock import Mock, patch

import pytest

from mcp_telecom.tools.interfaces import show_interface_detail


# We also verify the regex pattern is importable from the module
from mcp_telecom.tools.interfaces import _INTERFACE_RE


class TestInterfaceArgSanitization:
    """Test that show_interface_detail validates interface argument."""

    @pytest.mark.parametrize(
        "name",
        [
            "ge-0/0/0",
            "Ethernet0/0/0/1",
            "eth1/1",
            "GigabitEthernet0/0/1",
            "lag-1",
            "lo0",
            "Vlan100",
            "Port-Channel1",
        ],
    )
    def test_valid_interface_names_accepted(self, name: str):
        """Valid interface names should NOT be rejected by validation."""
        mock_dm = Mock()
        mock_audit = Mock()
        # The call will fail on device connection, but should NOT fail on validation
        result = show_interface_detail(mock_dm, mock_audit, "test-device", name)
        assert "invalid interface name" not in result.lower()

    @pytest.mark.parametrize(
        "name",
        [
            "ge-0/0/0; rm -rf /",
            "eth1|cat /etc/passwd",
            "eth1 && ls",
            "$(whoami)",
            "Ethernet`id`",
            "ge-0/0/0\nshow version",
        ],
    )
    def test_invalid_interface_names_rejected(self, name: str):
        """Interface names with shell metacharacters must be rejected."""
        mock_dm = Mock()
        mock_audit = Mock()
        result = show_interface_detail(mock_dm, mock_audit, "test-device", name)
        assert "invalid interface name" in result.lower()

    def test_interface_regex_pattern(self):
        """The _INTERFACE_RE pattern should match valid names and reject dangerous ones."""
        assert _INTERFACE_RE.fullmatch("ge-0/0/0") is not None
        assert _INTERFACE_RE.fullmatch("Ethernet0/0/0/1") is not None
        assert _INTERFACE_RE.fullmatch("ge-0/0/0; rm -rf /") is None
        assert _INTERFACE_RE.fullmatch("eth1|cat") is None
        assert _INTERFACE_RE.fullmatch("$(whoami)") is None
