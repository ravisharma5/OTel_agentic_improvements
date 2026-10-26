"""Tests for sdg.lib.flow_blocks (shared by Farbod's team, 2026-10-26),
the ToolTraceRendererBlock/ToolNameCleanerBlock that give the response judge
visibility into tool calls -- the stock flow passes only the final answer."""
from __future__ import annotations

import json

from sdg.lib.flow_blocks import (
    bare_tool_name,
    clean_target_tools,
    collapse_repeats,
    render_tool_trace,
    target_tool_names,
    truncate_middle,
    unwrap_tool_output,
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
                {"id": "2", "function": {"name": "tmf621createTroubleTicket", "arguments": '{"severity": "major"}'}}
            ],
        },
        {"role": "tool", "tool_call_id": "2", "content": "ticket 3180"},
    ]
)


def test_render_tool_trace_includes_each_call_result_and_answer():
    out = render_tool_trace(_TRACE, "Created ticket 3180.")
    assert "[assistant tool_call 1] tmf642listAlarm({})" in out
    assert "[tool result 1]\nok" in out
    assert '[assistant tool_call 2] tmf621createTroubleTicket({"severity": "major"})' in out
    assert "[tool result 2]\nticket 3180" in out
    assert out.endswith("[assistant final answer]\nCreated ticket 3180.")


def test_render_tool_trace_with_no_calls_says_so():
    out = render_tool_trace(None, "Just an answer, no tools needed.")
    assert out == "(the assistant made no tool calls)\n[assistant final answer]\nJust an answer, no tools needed."


def test_render_tool_trace_handles_missing_trace_gracefully():
    out = render_tool_trace("not valid json", "answer")
    assert "(the assistant made no tool calls)" in out


def test_render_tool_trace_truncates_per_result_when_total_exceeds_limit():
    # Varied, non-repeating content -- a single repeated character would be
    # shortened by collapse_repeats() before length-based truncation even
    # applies, which is correct behavior but not what this test is for.
    payload = "".join(f"line {i} has some unique content here\n" for i in range(200))
    huge_trace = json.dumps(
        [
            {"role": "assistant", "tool_calls": [{"id": str(i), "function": {"name": "f", "arguments": "{}"}}]}
            for i in range(5)
        ]
        + [{"role": "tool", "tool_call_id": str(i), "content": payload} for i in range(5)]
    )
    out = render_tool_trace(huge_trace, "done", max_result_chars=2000, max_total_chars=4000)
    assert "characters truncated" in out
    assert len(out) < len(payload) * 5  # well under unshortened size


def test_truncate_middle_keeps_head_and_tail():
    # limit must leave room for content beyond the marker's own ~40 chars.
    text = "a" * 50 + "b" * 50
    out = truncate_middle(text, 60)
    assert out.startswith("a")
    assert out.endswith("b")
    assert "characters truncated" in out


def test_truncate_middle_noop_under_limit():
    assert truncate_middle("short", 100) == "short"


def test_collapse_repeats_shortens_long_separator_runs():
    text = "before" + "=" * 500 + "after"
    out = collapse_repeats(text)
    assert out == "before" + "=" * 10 + "after"


def test_collapse_repeats_leaves_short_runs_alone():
    assert collapse_repeats("a---b") == "a---b"


def test_unwrap_tool_output_extracts_langchain_content():
    # The trace entry's "output" is an already-parsed dict at this point
    # (normalize_tool_trace's job), not a JSON-encoded string.
    raw = {"content": "the real payload", "additional_kwargs": {}}
    assert unwrap_tool_output(raw) == "the real payload"


def test_unwrap_tool_output_handles_missing_value():
    assert unwrap_tool_output(None) == ""


def test_bare_tool_name_strips_arguments():
    assert bare_tool_name("tmf642listAlarm(severity=major)") == "tmf642listAlarm"


def test_bare_tool_name_handles_plain_name():
    assert bare_tool_name("tmf642listAlarm") == "tmf642listAlarm"


def test_clean_target_tools_strips_args_from_tool_tags():
    value = "<tool>tmf642listAlarm(severity=major)</tool>\n<tool>tmf621createTroubleTicket()</tool>"
    out = clean_target_tools(value)
    assert out == "<tool>tmf642listAlarm</tool>\n<tool>tmf621createTroubleTicket</tool>"


def test_clean_target_tools_handles_missing_value():
    assert clean_target_tools(None) == ""


def test_target_tool_names_returns_bare_names_in_order():
    value = "<tool>tmf642listAlarm(severity=major)</tool>\n<tool>tmf621createTroubleTicket()</tool>"
    assert target_tool_names(value) == ["tmf642listAlarm", "tmf621createTroubleTicket"]
