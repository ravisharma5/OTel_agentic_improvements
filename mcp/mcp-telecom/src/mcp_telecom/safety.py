"""Command safety validation for MCP-Telecom.

Prevents dangerous or destructive commands from being executed
through the MCP server, ensuring read-only access by default.
"""

from __future__ import annotations

import re

BLOCKED_PATTERNS: list[str] = [
    r"\bconfigure\b",
    r"\bconfig\b\s+(terminal|t)",
    r"\bedit\b",
    r"\bset\b",
    r"\bdelete\b",
    r"\brollback\b",
    r"\bcommit\b",
    r"\bwrite\b\s+(memory|mem|terminal|erase)",
    r"\bcopy\b\s+running",
    r"\badmin\b\s+(save|reboot|shutdown|rollback)",
    r"\breboot\b",
    r"\breload\b",
    r"\bshutdown\b",
    r"\bno\s+shutdown\b",
    r"\bclear\b",
    r"\breset\b",
    r"\bformat\b",
    r"\berase\b",
    r"\bdestroy\b",
    r"\btools\b\s+(dump|perform)",
    r"\bdebug\b",
]

ALLOWED_PREFIXES = [
    "show",
    "display",
    "monitor",
    "ping",
    "traceroute",
    "tracepath",
]

_blocked_re = re.compile("|".join(BLOCKED_PATTERNS), re.IGNORECASE)


def is_safe_command(command: str) -> bool:
    """Check if a command is safe to execute (read-only).

    Returns True only if the command starts with an allowed prefix
    AND does not match any blocked pattern.
    """
    cmd = command.strip().lower()

    if not any(cmd.startswith(prefix) for prefix in ALLOWED_PREFIXES):
        return False

    if _blocked_re.search(cmd):
        return False

    return True


def validate_command(command: str) -> str | None:
    """Validate a command and return an error message if unsafe.

    Returns None if the command is safe, or an error string explaining why not.
    """
    cmd = command.strip()
    if not cmd:
        return "Empty command"

    if not is_safe_command(cmd):
        return (
            f"Command blocked for safety: '{cmd}'. "
            f"Only read-only commands are allowed (show, display, ping, traceroute). "
            f"Configuration changes must be made through your standard change management process."
        )

    return None
