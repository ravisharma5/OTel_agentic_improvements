"""Tests for the audit logger."""

import json
import os
import tempfile

from mcp_telecom.audit import AuditLogger


class TestAuditLogger:
    def test_log_and_read(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            tmp_path = f.name

        try:
            logger = AuditLogger(tmp_path)
            logger.log_command(
                device="router1",
                command="show version",
                tool="test_tool",
                success=True,
                output_length=100,
            )

            entries = logger.get_recent_entries()
            assert len(entries) == 1
            assert entries[0]["device"] == "router1"
            assert entries[0]["command"] == "show version"
            assert entries[0]["success"] is True
        finally:
            os.unlink(tmp_path)

    def test_log_failure(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            tmp_path = f.name

        try:
            logger = AuditLogger(tmp_path)
            logger.log_command(
                device="router1",
                command="show version",
                tool="test_tool",
                success=False,
                error="Connection timeout",
            )

            entries = logger.get_recent_entries()
            assert len(entries) == 1
            assert entries[0]["success"] is False
            assert "timeout" in entries[0]["error"].lower()
        finally:
            os.unlink(tmp_path)

    def test_multiple_entries(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            tmp_path = f.name

        try:
            logger = AuditLogger(tmp_path)
            for i in range(5):
                logger.log_command(
                    device=f"router{i}",
                    command="show version",
                    tool="test",
                    success=True,
                )

            entries = logger.get_recent_entries(3)
            assert len(entries) == 3
            assert entries[0]["device"] == "router2"
        finally:
            os.unlink(tmp_path)

    def test_empty_log(self):
        logger = AuditLogger("/tmp/nonexistent_audit_test.log")
        entries = logger.get_recent_entries()
        assert entries == []

    def test_entries_are_valid_json(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".log", delete=False) as f:
            tmp_path = f.name

        try:
            logger = AuditLogger(tmp_path)
            logger.log_command("r1", "show ver", "test", True, 50)

            with open(tmp_path) as f:
                line = f.readline().strip()
                data = json.loads(line)
                assert "timestamp" in data
                assert "device" in data
        finally:
            os.unlink(tmp_path)
