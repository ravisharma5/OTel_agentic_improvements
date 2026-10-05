"""Tests for OSFT schema compliance validation library.

Validates that validate_osft_line and validate_osft_file correctly
detect missing fields, broken tool_call_id threading, empty messages,
invalid JSON function arguments, and other schema violations.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from sdg.lib.osft_validation import validate_osft_file, validate_osft_line


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _valid_osft_line() -> dict:
    """Return a fully valid OSFT line with proper tool_call_id threading."""
    return {
        "messages": [
            {
                "role": "system",
                "content": "You are a telecom assistant with tools.",
            },
            {
                "role": "user",
                "content": "Check for critical alarms.",
            },
            {
                "role": "assistant",
                "content": None,
                "tool_calls": [
                    {
                        "id": "call_abc123",
                        "type": "function",
                        "function": {
                            "name": "tmf642_list_alarms",
                            "arguments": '{"severity": "critical"}',
                        },
                    },
                ],
            },
            {
                "role": "tool",
                "tool_call_id": "call_abc123",
                "content": '{"count": 1}',
            },
            {
                "role": "assistant",
                "content": "Found one critical alarm.",
            },
        ],
    }


# ---------------------------------------------------------------------------
# Test classes
# ---------------------------------------------------------------------------


class TestValidOSFT:
    """Valid OSFT lines should produce no errors."""

    def test_valid_line_no_errors(self) -> None:
        assert validate_osft_line(_valid_osft_line()) == []

    def test_valid_line_with_multiple_tool_calls(self) -> None:
        line = _valid_osft_line()
        # Add a second tool call
        line["messages"][2]["tool_calls"].append(
            {
                "id": "call_def456",
                "type": "function",
                "function": {
                    "name": "tmf628_get_performance",
                    "arguments": '{"kpi": "pmActiveUEDlMean"}',
                },
            }
        )
        # Add corresponding tool response
        line["messages"].insert(
            4,
            {
                "role": "tool",
                "tool_call_id": "call_def456",
                "content": '{"value": 42.5}',
            },
        )
        assert validate_osft_line(line) == []

    def test_valid_line_system_user_assistant_only(self) -> None:
        """A simple conversation without tool calls is valid."""
        line = {
            "messages": [
                {"role": "system", "content": "You are a helper."},
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
            ],
        }
        assert validate_osft_line(line) == []


class TestInvalidOSFT:
    """Invalid OSFT lines should produce descriptive errors."""

    def test_missing_messages(self) -> None:
        errors = validate_osft_line({})
        assert len(errors) > 0
        assert any("messages" in e.lower() for e in errors)

    def test_empty_messages(self) -> None:
        errors = validate_osft_line({"messages": []})
        assert len(errors) > 0
        assert any("empty" in e.lower() for e in errors)

    def test_messages_not_a_list(self) -> None:
        errors = validate_osft_line({"messages": "not a list"})
        assert len(errors) > 0

    def test_missing_role(self) -> None:
        line = _valid_osft_line()
        del line["messages"][1]["role"]
        errors = validate_osft_line(line)
        assert any("role" in e.lower() for e in errors)

    def test_invalid_role(self) -> None:
        line = _valid_osft_line()
        line["messages"][1]["role"] = "unknown_role"
        errors = validate_osft_line(line)
        assert any("role" in e.lower() for e in errors)

    def test_missing_tool_call_id(self) -> None:
        line = _valid_osft_line()
        del line["messages"][3]["tool_call_id"]
        errors = validate_osft_line(line)
        assert any("tool_call_id" in e.lower() for e in errors)

    def test_mismatched_tool_call_id(self) -> None:
        line = _valid_osft_line()
        line["messages"][3]["tool_call_id"] = "call_nonexistent999"
        errors = validate_osft_line(line)
        assert any("no matching" in e.lower() or "tool_calls" in e.lower() for e in errors)

    def test_assistant_tool_calls_missing_id(self) -> None:
        line = _valid_osft_line()
        del line["messages"][2]["tool_calls"][0]["id"]
        errors = validate_osft_line(line)
        assert any("id" in e.lower() for e in errors)

    def test_assistant_tool_calls_missing_function(self) -> None:
        line = _valid_osft_line()
        del line["messages"][2]["tool_calls"][0]["function"]
        errors = validate_osft_line(line)
        assert any("function" in e.lower() for e in errors)

    def test_invalid_function_arguments(self) -> None:
        line = _valid_osft_line()
        line["messages"][2]["tool_calls"][0]["function"]["arguments"] = "not valid json{"
        errors = validate_osft_line(line)
        assert any("arguments" in e.lower() for e in errors)

    def test_tool_calls_missing_type(self) -> None:
        line = _valid_osft_line()
        del line["messages"][2]["tool_calls"][0]["type"]
        errors = validate_osft_line(line)
        assert any("type" in e.lower() for e in errors)

    def test_function_missing_name(self) -> None:
        line = _valid_osft_line()
        del line["messages"][2]["tool_calls"][0]["function"]["name"]
        errors = validate_osft_line(line)
        assert any("name" in e.lower() for e in errors)

    def test_tool_message_missing_content(self) -> None:
        line = _valid_osft_line()
        del line["messages"][3]["content"]
        errors = validate_osft_line(line)
        assert any("content" in e.lower() for e in errors)

    def test_assistant_no_content_and_no_tool_calls(self) -> None:
        line = _valid_osft_line()
        # Make assistant message have neither content nor tool_calls
        line["messages"][2] = {"role": "assistant"}
        errors = validate_osft_line(line)
        assert len(errors) > 0


class TestFileValidation:
    """File-level validation with line number tracking."""

    def test_valid_file(self, tmp_path: Path) -> None:
        filepath = tmp_path / "valid.jsonl"
        filepath.write_text(json.dumps(_valid_osft_line()) + "\n")
        is_valid, errors = validate_osft_file(str(filepath))
        assert is_valid is True
        assert errors == []

    def test_invalid_file(self, tmp_path: Path) -> None:
        filepath = tmp_path / "invalid.jsonl"
        invalid = {"messages": []}
        filepath.write_text(json.dumps(invalid) + "\n")
        is_valid, errors = validate_osft_file(str(filepath))
        assert is_valid is False
        assert len(errors) > 0

    def test_mixed_file(self, tmp_path: Path) -> None:
        filepath = tmp_path / "mixed.jsonl"
        valid_line = json.dumps(_valid_osft_line())
        invalid_line = json.dumps({"messages": []})
        filepath.write_text(valid_line + "\n" + invalid_line + "\n")
        is_valid, errors = validate_osft_file(str(filepath))
        assert is_valid is False
        assert len(errors) > 0
        # Error should reference line 2
        assert any("2" in e for e in errors)

    def test_empty_lines_skipped(self, tmp_path: Path) -> None:
        filepath = tmp_path / "empty_lines.jsonl"
        valid_line = json.dumps(_valid_osft_line())
        filepath.write_text(valid_line + "\n\n\n")
        is_valid, errors = validate_osft_file(str(filepath))
        assert is_valid is True
        assert errors == []

    def test_malformed_json_line(self, tmp_path: Path) -> None:
        filepath = tmp_path / "malformed.jsonl"
        filepath.write_text("not json at all\n")
        is_valid, errors = validate_osft_file(str(filepath))
        assert is_valid is False
        assert any("json" in e.lower() or "parse" in e.lower() for e in errors)

    def test_multi_valid_lines(self, tmp_path: Path) -> None:
        filepath = tmp_path / "multi_valid.jsonl"
        lines = [json.dumps(_valid_osft_line()) for _ in range(5)]
        filepath.write_text("\n".join(lines) + "\n")
        is_valid, errors = validate_osft_file(str(filepath))
        assert is_valid is True
        assert errors == []
