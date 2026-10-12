"""Tests for tool_coverage_report.py.

Covers the two things most likely to be wrong on a first real run: the
assumed trace-column name not matching sdg_hub's actual output (handled via
_find_trace_column's fallback search, not a silent miss), and the
never-called-tools computation actually reflecting the full in-scope set
from seed-scenarios.yaml rather than just what appears in the examples.
"""
from __future__ import annotations

import json

from sdg.scripts.tool_coverage_report import (
    DEFAULT_TRACE_COLUMN,
    _find_trace_column,
    build_coverage_report,
    render_markdown,
)


def _example(scenario_name, tier, intended_tools, called_tools, trace_col=DEFAULT_TRACE_COLUMN):
    trace = [{"type": "tool_use", "name": t, "tool_input": {}, "output": "{}"} for t in called_tools]
    return {
        "scenario_name": scenario_name,
        "tier": tier,
        "intended_tools": intended_tools,
        trace_col: json.dumps(trace),
    }


class TestFindTraceColumn:
    def test_finds_preferred_column(self) -> None:
        row = {DEFAULT_TRACE_COLUMN: "[]", "other": 1}
        assert _find_trace_column(row, DEFAULT_TRACE_COLUMN) == DEFAULT_TRACE_COLUMN

    def test_falls_back_to_any_tool_trace_named_column(self) -> None:
        row = {"some_other_tool_trace_field": "[]"}
        assert _find_trace_column(row, DEFAULT_TRACE_COLUMN) == "some_other_tool_trace_field"

    def test_returns_none_when_no_match(self) -> None:
        row = {"question": "x", "answer": "y"}
        assert _find_trace_column(row, DEFAULT_TRACE_COLUMN) is None


class TestBuildCoverageReport:
    def test_tools_never_called_computed_against_full_in_scope_set(self) -> None:
        examples = [_example("s1", "single_tool", ["tool_a"], ["tool_a"])]
        report = build_coverage_report(examples, {"tool_a", "tool_b", "tool_c"})
        assert report["tools_never_called"] == ["tool_b", "tool_c"]

    def test_global_tool_call_counts_aggregate_across_scenarios(self) -> None:
        examples = [
            _example("s1", "single_tool", ["tool_a"], ["tool_a"]),
            _example("s2", "parallel", ["tool_a", "tool_b"], ["tool_a", "tool_b"]),
        ]
        report = build_coverage_report(examples, {"tool_a", "tool_b"})
        assert report["tool_call_counts"]["tool_a"] == 2
        assert report["tool_call_counts"]["tool_b"] == 1

    def test_per_scenario_breakdown_flags_intended_but_never_called(self) -> None:
        # Scenario intends two tools but the trajectory only called one --
        # e.g. the agent answered without needing the second tool.
        examples = [_example("s1", "sequential", ["tool_a", "tool_b"], ["tool_a"])]
        report = build_coverage_report(examples, {"tool_a", "tool_b"})
        s1 = report["scenarios"]["s1"]
        assert s1["intended_tools_never_called_in_this_scenario"] == ["tool_b"]
        assert s1["examples_generated"] == 1

    def test_missing_trace_column_counted_not_silently_dropped(self) -> None:
        examples = [{"scenario_name": "s1", "tier": "single_tool", "intended_tools": ["tool_a"]}]
        report = build_coverage_report(examples, {"tool_a"})
        assert report["examples_missing_trace"] == 1
        assert report["tools_never_called"] == ["tool_a"]

    def test_multiple_examples_same_scenario_aggregate(self) -> None:
        examples = [
            _example("s1", "single_tool", ["tool_a"], ["tool_a"]),
            _example("s1", "single_tool", ["tool_a"], ["tool_a"]),
            _example("s1", "single_tool", ["tool_a"], []),
        ]
        report = build_coverage_report(examples, {"tool_a"})
        assert report["scenarios"]["s1"]["examples_generated"] == 3
        assert report["scenarios"]["s1"]["tools_actually_called"]["tool_a"] == 2


class TestRenderMarkdown:
    def test_renders_without_error_and_includes_key_sections(self) -> None:
        examples = [_example("s1", "single_tool", ["tool_a"], ["tool_a"])]
        report = build_coverage_report(examples, {"tool_a", "tool_b"})
        md = render_markdown(report)
        assert "# Tool Coverage Report" in md
        assert "## Tools Never Called" in md
        assert "tool_b" in md
        assert "s1" in md

    def test_warns_in_markdown_when_trace_missing(self) -> None:
        examples = [{"scenario_name": "s1", "tier": "single_tool", "intended_tools": []}]
        report = build_coverage_report(examples, set())
        md = render_markdown(report)
        assert "WARNING" in md
