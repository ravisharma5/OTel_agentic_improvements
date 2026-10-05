"""Tests for backup file path containment in compare_configs (CR-03).

Verifies that compare_configs only reads files within the backups/ directory.
Path traversal attempts are REJECTED (return error), NOT silently remapped
to a different file inside backups/.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest

from mcp_telecom import server
from mcp_telecom.server import compare_configs, BACKUPS_DIR


class TestBackupFileContainment:
    """Test that compare_configs contains file reads to backups/ directory."""

    @pytest.fixture(autouse=True)
    def _setup_backups(self, tmp_path, monkeypatch):
        """Set up a temporary backups directory with test files."""
        backups_dir = tmp_path / "backups"
        backups_dir.mkdir()

        # Write a legitimate backup file
        (backups_dir / "backup.cfg").write_text("hostname test-router")

        # Write a DECOY file named "passwd" inside backups/ -- this is critical
        # for proving traversal is REJECTED, not silently remapped.
        # If compare_configs("../../etc/passwd") returns the content of this file,
        # it means .name was used to strip the path, which is the bug CR-03 fixes.
        (backups_dir / "passwd").write_text("decoy - this should NOT be read by traversal")

        # Monkeypatch BACKUPS_DIR to point at our tmp backups
        monkeypatch.setattr(server, "BACKUPS_DIR", backups_dir.resolve())

    def test_traversal_is_rejected_not_remapped(self):
        """Path traversal must be REJECTED, not silently remapped to backups/passwd."""
        result = compare_configs("test-device", "../../etc/passwd")
        # Must return an error about the backups/ directory
        assert "backups" in result.lower() or "Error" in result
        # Must NOT contain the decoy file content
        assert "decoy" not in result

    def test_absolute_path_rejected(self):
        """Absolute path must be rejected."""
        result = compare_configs("test-device", "/etc/shadow")
        assert "backups" in result.lower() or "Error" in result

    def test_nested_traversal_rejected(self):
        """Nested traversal like sub/../../../etc/passwd must be rejected."""
        result = compare_configs("test-device", "sub/../../../etc/passwd")
        assert "backups" in result.lower() or "Error" in result

    def test_valid_backup_file_accepted(self):
        """A valid backup file inside backups/ should not trigger containment error."""
        # Mock device connection since we can't actually connect to devices
        mock_config = Mock()
        mock_conn = MagicMock()
        mock_conn.__enter__ = Mock(return_value=mock_conn)
        mock_conn.__exit__ = Mock(return_value=False)
        mock_conn.send_command.return_value = "hostname test-router-updated"

        with patch.object(server.device_manager, "get_device", return_value=mock_config), \
             patch.object(server.device_manager, "connect", return_value=mock_conn), \
             patch("mcp_telecom.server.get_command", return_value="show running-config"):
            result = compare_configs("test-device", "backup.cfg")

        # Should NOT contain the containment error message
        assert "must be within the backups" not in result
