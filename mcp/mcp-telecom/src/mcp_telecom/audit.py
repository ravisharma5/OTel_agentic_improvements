"""Audit logging for MCP-Telecom.

Records every command executed through the MCP server for
compliance, debugging, and security review.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("mcp_telecom.audit")


class AuditLogger:
    """Structured audit logger that writes command executions to a JSONL file."""

    def __init__(self, log_path: str | None = None):
        self._log_path = log_path or os.getenv("MCP_TELECOM_AUDIT_LOG", "logs/audit.log")
        self._ensure_directory()

    def _ensure_directory(self) -> None:
        Path(self._log_path).parent.mkdir(parents=True, exist_ok=True)

    def log_command(
        self,
        device: str,
        command: str,
        tool: str,
        success: bool,
        output_length: int = 0,
        error: str | None = None,
    ) -> None:
        """Log a command execution event."""
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "device": device,
            "command": command,
            "tool": tool,
            "success": success,
            "output_length": output_length,
        }
        if error:
            entry["error"] = error

        try:
            with open(self._log_path, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception as e:
            logger.error("Failed to write audit log: %s", e)

    def get_recent_entries(self, count: int = 50) -> list[dict]:
        """Read the most recent audit log entries."""
        path = Path(self._log_path)
        if not path.exists():
            return []

        entries = []
        try:
            with open(path) as f:
                for line in f:
                    line = line.strip()
                    if line:
                        entries.append(json.loads(line))
        except Exception as e:
            logger.error("Failed to read audit log: %s", e)

        return entries[-count:]
