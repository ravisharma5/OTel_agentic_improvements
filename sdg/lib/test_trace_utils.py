"""Tests for sdg.lib.trace_utils, focused on the tool-coverage gate added
for the KFP rejection-sampling pipeline (04-LEARNINGS.md, 2026-10-09)."""
from __future__ import annotations

import json

from sdg.lib.trace_utils import (
    DEFAULT_TRACE_COLUMN,
    find_trace_column,
    normalize_tool_trace,
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


def test_normalize_tool_trace_parses_json_encoded_tool_content():
    """Regression test for #1's follow-up: a tool-role message's `content`
    is a JSON-encoded string of the full LangChain ToolMessage dict
    (additional_kwargs/response_metadata/artifact noise plus the real
    response), not the bare backend response. normalize_tool_trace must
    parse it into a dict so serialize_osft.py's _extract_tool_output_content
    can strip it down -- leaving it as a raw string defeats that entirely
    (isinstance(output, str) short-circuits and returns the whole blob)."""
    raw_tool_content = json.dumps(
        {
            "content": '{"result": [{"id": "8675309"}]}',
            "additional_kwargs": {},
            "response_metadata": {},
            "type": "tool",
            "name": "tmf642listAlarm",
            "tool_call_id": "1",
            "artifact": {"structuredContent": {"result": [{"id": "8675309"}]}},
            "status": "success",
        }
    )
    trace = [
        {
            "role": "assistant",
            "tool_calls": [
                {"id": "1", "function": {"name": "tmf642listAlarm", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "tool_call_id": "1", "content": raw_tool_content},
    ]
    normalized = normalize_tool_trace(trace)
    assert len(normalized) == 1
    output = normalized[0]["output"]
    assert isinstance(output, dict), "output must be parsed, not left as a raw JSON string"
    assert output["content"] == '{"result": [{"id": "8675309"}]}'


def test_normalize_tool_trace_falls_back_to_raw_string_for_non_json_content():
    """A tool error or plain-text response isn't JSON -- must not crash,
    and must preserve the original content rather than dropping it."""
    trace = [
        {
            "role": "assistant",
            "tool_calls": [
                {"id": "1", "function": {"name": "tmf642listAlarm", "arguments": "{}"}}
            ],
        },
        {"role": "tool", "tool_call_id": "1", "content": "connection timed out"},
    ]
    normalized = normalize_tool_trace(trace)
    assert normalized[0]["output"] == "connection timed out"
