"""Command safety validation for MCP-Telecom.

Prevents dangerous or destructive commands from being executed
through the MCP server, ensuring read-only access by default.

CR-01: validate_command() enforces command_allowlist.yaml deny-by-default.
Commands must pass BOTH the safety regex check AND the allowlist prefix match.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml

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

# ── Allowlist enforcement (CR-01) ──────────────────────────────────────────
# Deny-by-default: commands must match an allowlist prefix in addition to
# passing the safety regex check. Empty allowlist = deny all commands.

_allowlist_cache: list[str] | None = None


def _load_allowlist() -> list[str]:
    """Load the command allowlist from YAML, with caching.

    Resolves the allowlist file path from the MCP_TELECOM_ALLOWLIST_FILE
    environment variable (read dynamically each time the cache is empty,
    NOT as a module-level constant). Falls back to the default
    command_allowlist.yaml location relative to this package.

    Returns an empty list if the file does not exist (deny all).
    """
    global _allowlist_cache
    if _allowlist_cache is not None:
        return _allowlist_cache

    default_path = str(Path(__file__).parent.parent.parent / "command_allowlist.yaml")
    allowlist_path = os.getenv("MCP_TELECOM_ALLOWLIST_FILE", default_path)

    path = Path(allowlist_path)
    if not path.exists():
        _allowlist_cache = []
        return _allowlist_cache

    try:
        data = yaml.safe_load(path.read_text())
        if data is None:
            _allowlist_cache = []
        else:
            _allowlist_cache = data.get("allowed_commands", []) or []
    except Exception:
        _allowlist_cache = []

    return _allowlist_cache


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

    Two sequential gates (CR-01):
    1. is_safe_command() -- regex safety check (read-only prefixes, no blocked patterns)
    2. Allowlist prefix match -- command must match a prefix in command_allowlist.yaml
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

    # Gate 2: allowlist enforcement (CR-01)
    allowlist = _load_allowlist()
    if not allowlist:
        return (
            "Command blocked: command_allowlist.yaml has no allowed commands. "
            "Populate the allowlist before executing commands on devices."
        )

    if not any(cmd.lower().startswith(prefix.lower()) for prefix in allowlist):
        return "Command blocked: not in command_allowlist.yaml allowed list."

    return None
