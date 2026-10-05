"""OSFT schema compliance validation library.

Provides validate_osft_line and validate_osft_file for checking OSFT
JSONL format compliance including tool_call_id threading, required
fields, and valid JSON function arguments.

Per amended D-04, these functions are imported by run-evaluation.py
(Plan 07) and called automatically after the eval flow completes --
this is a library module, not a standalone script.
"""
from __future__ import annotations

import json
from pathlib import Path

_VALID_ROLES = {"system", "user", "assistant", "tool"}


def validate_osft_line(line: dict) -> list[str]:
    """Validate a single OSFT JSONL line for schema compliance.

    Checks:
        - ``messages`` key exists and is a non-empty list
        - Every message has a valid ``role``
        - Tool messages have ``tool_call_id`` matching a prior assistant
          ``tool_calls[].id``
        - Tool messages have ``content``
        - Assistant messages with ``tool_calls`` have properly structured
          entries (id, type, function with name and arguments)
        - Function ``arguments`` is a valid JSON string
        - Assistant messages have either ``content`` or ``tool_calls``

    Args:
        line: A single parsed OSFT JSONL record (dict).

    Returns:
        List of error description strings. Empty list means valid.
    """
    errors: list[str] = []

    # --- messages key ---
    if "messages" not in line:
        errors.append("Missing 'messages' key")
        return errors

    messages = line["messages"]
    if not isinstance(messages, list):
        errors.append("'messages' must be a list")
        return errors

    if len(messages) == 0:
        errors.append("'messages' is empty")
        return errors

    # Collect all tool_call IDs from assistant messages for cross-reference
    all_tool_call_ids: set[str] = set()

    for idx, msg in enumerate(messages):
        prefix = f"Message {idx}"

        # --- role ---
        if "role" not in msg:
            errors.append(f"{prefix}: missing 'role'")
            continue

        role = msg["role"]
        if role not in _VALID_ROLES:
            errors.append(
                f"{prefix}: invalid role '{role}' "
                f"(must be one of {sorted(_VALID_ROLES)})"
            )
            continue

        # --- assistant messages ---
        if role == "assistant":
            has_content = "content" in msg and msg["content"] is not None
            has_tool_calls = "tool_calls" in msg and msg["tool_calls"]

            if not has_content and not has_tool_calls:
                errors.append(
                    f"{prefix}: assistant message must have 'content' "
                    f"or non-empty 'tool_calls'"
                )

            if has_tool_calls:
                for tc_idx, tc in enumerate(msg["tool_calls"]):
                    tc_prefix = f"{prefix}, tool_calls[{tc_idx}]"

                    if "id" not in tc:
                        errors.append(f"{tc_prefix}: missing 'id'")
                    else:
                        all_tool_call_ids.add(tc["id"])

                    if "type" not in tc:
                        errors.append(f"{tc_prefix}: missing 'type'")

                    if "function" not in tc:
                        errors.append(f"{tc_prefix}: missing 'function'")
                    else:
                        fn = tc["function"]
                        if "name" not in fn:
                            errors.append(
                                f"{tc_prefix}: function missing 'name'"
                            )
                        if "arguments" not in fn:
                            errors.append(
                                f"{tc_prefix}: function missing 'arguments'"
                            )
                        elif isinstance(fn["arguments"], str):
                            try:
                                json.loads(fn["arguments"])
                            except (json.JSONDecodeError, ValueError):
                                errors.append(
                                    f"{tc_prefix}: function 'arguments' "
                                    f"is not valid JSON"
                                )

        # --- tool messages ---
        elif role == "tool":
            if "tool_call_id" not in msg:
                errors.append(f"{prefix}: tool message missing 'tool_call_id'")
            elif msg["tool_call_id"] not in all_tool_call_ids:
                errors.append(
                    f"{prefix}: tool_call_id '{msg['tool_call_id']}' "
                    f"has no matching tool_calls[].id in a prior "
                    f"assistant message"
                )

            if "content" not in msg:
                errors.append(f"{prefix}: tool message missing 'content'")

    return errors


def validate_osft_file(path: str) -> tuple[bool, list[str]]:
    """Validate an OSFT JSONL file for schema compliance.

    Reads the file line by line, parses each as JSON, and runs
    ``validate_osft_line`` on each parsed record. Collects errors
    with line numbers.

    Args:
        path: Path to the JSONL file.

    Returns:
        Tuple of (is_valid, errors_list). ``is_valid`` is True when
        all lines pass validation. ``errors_list`` contains error
        strings prefixed with line numbers.
    """
    all_errors: list[str] = []
    filepath = Path(path)

    with filepath.open() as f:
        for line_no, raw_line in enumerate(f, start=1):
            raw_line = raw_line.strip()
            if not raw_line:
                continue

            try:
                parsed = json.loads(raw_line)
            except (json.JSONDecodeError, ValueError) as exc:
                all_errors.append(
                    f"Line {line_no}: JSON parse error: {exc}"
                )
                continue

            line_errors = validate_osft_line(parsed)
            for err in line_errors:
                all_errors.append(f"Line {line_no}: {err}")

    return (len(all_errors) == 0, all_errors)
