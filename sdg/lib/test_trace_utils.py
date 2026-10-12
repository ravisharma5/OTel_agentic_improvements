"""Tests for sdg.lib.trace_utils, focused on the tool-coverage gate added
for the KFP rejection-sampling pipeline (04-LEARNINGS.md, 2026-10-09)."""
from __future__ import annotations

import json

from sdg.lib.trace_utils import (
    DEFAULT_TRACE_COLUMN,
    find_trace_column,
    row_passes_tool_coverage,
    tools_called_in_row,
)

_TRACE = json.dumps(
    [
        {
            "role": "assistant",
            "tool_calls": [
                {"id": "1", "function": {"name": "tmf642listAlarm", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "tool_call_id": "1", "content": "ok"},
        {
            "role": "assistant",
            "tool_calls": [
                {"id": "2", "function": {"name": "tmf621createTroubleTicket", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "tool_call_id": "2", "content": "ok"},
    ]
)


def test_find_trace_column_prefers_default_name():
    row = {DEFAULT_TRACE_COLUMN: "[]", "other_tool_trace_thing": "[]"}
    assert find_trace_column(row) == DEFAULT_TRACE_COLUMN


def test_find_trace_column_falls_back_to_fuzzy_match():
    row = {"some_other_tool_trace_column": "[]"}
    assert find_trace_column(row) == "some_other_tool_trace_column"


def test_find_trace_column_returns_none_when_absent():
    row = {"unrelated": "value"}
    assert find_trace_column(row) is None


def test_tools_called_in_row_extracts_names():
    row = {DEFAULT_TRACE_COLUMN: _TRACE}
    assert tools_called_in_row(row) == ["tmf642listAlarm", "tmf621createTroubleTicket"]


def test_row_passes_tool_coverage_when_all_intended_tools_called():
    row = {
        DEFAULT_TRACE_COLUMN: _TRACE,
        "intended_tools": ["tmf642listAlarm", "tmf621createTroubleTicket"],
    }
    assert row_passes_tool_coverage(row) is True


def test_row_fails_tool_coverage_when_intended_tool_missing():
    row = {
        DEFAULT_TRACE_COLUMN: _TRACE,
        "intended_tools": ["tmf642listAlarm", "nwdafget_nwdaf_analytics"],
    }
    assert row_passes_tool_coverage(row) is False


def test_row_without_intended_tools_passes_by_default():
    row = {DEFAULT_TRACE_COLUMN: "[]", "intended_tools": []}
    assert row_passes_tool_coverage(row) is True


def test_row_missing_intended_tools_key_passes_by_default():
    row = {DEFAULT_TRACE_COLUMN: "[]"}
    assert row_passes_tool_coverage(row) is True


def test_row_with_no_trace_column_fails_when_tools_intended():
    row = {"intended_tools": ["tmf642listAlarm"]}
    assert row_passes_tool_coverage(row) is False
