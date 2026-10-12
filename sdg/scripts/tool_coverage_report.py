#!/usr/bin/env python3
"""Report which tools generated SDG examples actually called, per scenario.

Cross-references each generated example's actual tool trace (extracted by
sdg_hub's flow via AgentResponseExtractorBlock's extract_tool_trace=True)
against the seed scenario it came from (sdg/config/seed-scenarios.yaml,
carried through generation as the mcp_server_name/scenario_name/
intended_tools passthrough columns -- see materialize_seeds.py). Answers,
per scenario and globally: which tools were actually exercised, how that
compares to what the scenario's tool_subset intended, and which of the
in-scope tools were never called by anything.

Written for documentation/blog purposes as much as pipeline QA: a dataset
description that says "100 examples across 5 tiers" is a lot less useful
than one that also says which of the 20 in-scope tools never got exercised.

Usage:
    python -m sdg.scripts.tool_coverage_report \\
        --input sdg/data/raw/dry-run/all_tiers_raw.jsonl \\
        --seed-scenarios sdg/config/seed-scenarios.yaml \\
        --output-dir sdg/data/raw/dry-run/

Requires: sdg.lib.trace_utils (vendored sdg_hub normalize_tool_trace)
"""
from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import yaml

from sdg.lib.trace_utils import (
    DEFAULT_TRACE_COLUMN,
    extract_tool_names,
    find_trace_column as _find_trace_column,
    normalize_tool_trace,
)


def build_coverage_report(
    examples: list[dict],
    all_in_scope_tools: set[str],
    trace_column: str = DEFAULT_TRACE_COLUMN,
) -> dict:
    """Build a structured coverage report from generated examples.

    Args:
        examples: Generated rows (post flow.generate()), each expected to
            carry scenario_name/tier/intended_tools (materialize_seeds.py
            passthrough columns) and a tool-trace column.
        all_in_scope_tools: Full set of tool names considered in scope
            (e.g. the union of every seed-scenarios.yaml tool_subset) --
            used to compute which tools were never called by anything.
        trace_column: Expected tool-trace column name (see _find_trace_column).

    Returns:
        Dict with 'scenarios' (per-scenario breakdown), 'tool_call_counts'
        (global histogram), 'tools_never_called', and 'examples_missing_trace'
        (rows where no trace column could be found, reported so a wrong
        DEFAULT_TRACE_COLUMN guess is visible rather than silently ignored).
    """
    per_scenario: dict[str, dict] = defaultdict(
        lambda: {
            "tier": None,
            "intended_tools": [],
            "examples_generated": 0,
            "tools_called": Counter(),
        }
    )
    global_tool_calls: Counter = Counter()
    missing_trace = 0

    for row in examples:
        scenario = row.get("scenario_name") or row.get("mcp_server_name") or "<unknown>"
        entry = per_scenario[scenario]
        entry["tier"] = row.get("tier", entry["tier"])
        if row.get("intended_tools"):
            entry["intended_tools"] = row["intended_tools"]
        entry["examples_generated"] += 1

        col = _find_trace_column(row, trace_column)
        if col is None:
            missing_trace += 1
            continue

        raw_trace = row.get(col)
        if not raw_trace:
            continue
        called = extract_tool_names(normalize_tool_trace(raw_trace))
        entry["tools_called"].update(called)
        global_tool_calls.update(called)

    scenarios_out = {}
    for name, entry in per_scenario.items():
        called_set = set(entry["tools_called"])
        intended_set = set(entry["intended_tools"])
        scenarios_out[name] = {
            "tier": entry["tier"],
            "intended_tools": sorted(intended_set),
            "examples_generated": entry["examples_generated"],
            "tools_actually_called": dict(entry["tools_called"]),
            "intended_tools_never_called_in_this_scenario": sorted(intended_set - called_set),
        }

    tools_never_called = sorted(all_in_scope_tools - set(global_tool_calls))

    return {
        "scenarios": scenarios_out,
        "tool_call_counts": dict(global_tool_calls.most_common()),
        "tools_never_called": tools_never_called,
        "examples_missing_trace": missing_trace,
        "total_examples": len(examples),
    }


def render_markdown(report: dict) -> str:
    """Render the coverage report as a human-readable Markdown document."""
    lines = ["# Tool Coverage Report", ""]
    lines.append(f"Total examples analyzed: {report['total_examples']}")
    if report["examples_missing_trace"]:
        lines.append(
            f"\n**WARNING:** {report['examples_missing_trace']} example(s) had no "
            "recognizable tool-trace column -- check --trace-column against the "
            "actual generated output's columns."
        )
    lines.append("")

    lines.append("## Tools Never Called")
    if report["tools_never_called"]:
        for tool in report["tools_never_called"]:
            lines.append(f"- `{tool}`")
    else:
        lines.append("None -- every in-scope tool was called at least once.")
    lines.append("")

    lines.append("## Global Tool Call Counts")
    lines.append("")
    lines.append("| Tool | Calls |")
    lines.append("|---|---|")
    for tool, count in report["tool_call_counts"].items():
        lines.append(f"| `{tool}` | {count} |")
    lines.append("")

    lines.append("## Per-Scenario Breakdown")
    for name, s in sorted(report["scenarios"].items(), key=lambda kv: (kv[1]["tier"] or "", kv[0])):
        lines.append(f"\n### {name} (tier: {s['tier']})")
        lines.append(f"- Examples generated: {s['examples_generated']}")
        lines.append(f"- Intended tools: {', '.join(f'`{t}`' for t in s['intended_tools']) or '(none)'}")
        if s["tools_actually_called"]:
            called_str = ", ".join(f"`{t}` ({c})" for t, c in s["tools_actually_called"].items())
            lines.append(f"- Tools actually called: {called_str}")
        else:
            lines.append("- Tools actually called: none")
        if s["intended_tools_never_called_in_this_scenario"]:
            never = ", ".join(f"`{t}`" for t in s["intended_tools_never_called_in_this_scenario"])
            lines.append(f"- Intended but never called in this scenario: {never}")

    return "\n".join(lines) + "\n"


def _load_in_scope_tools(seed_scenarios_path: Path) -> set[str]:
    config = yaml.safe_load(seed_scenarios_path.read_text())
    tools: set[str] = set()
    for tier in config.get("tiers", {}).values():
        for scenario in tier.get("scenarios", []):
            tools.update(scenario.get("tool_subset", []))
    return tools


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="Generated examples JSONL (post flow.generate()).")
    parser.add_argument(
        "--seed-scenarios",
        default="sdg/config/seed-scenarios.yaml",
        help="Path to seed-scenarios.yaml, used to compute the in-scope tool set.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory to write report files.")
    parser.add_argument(
        "--trace-column",
        default=DEFAULT_TRACE_COLUMN,
        help=f"Expected tool-trace column name (default: {DEFAULT_TRACE_COLUMN}).",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)

    examples = []
    with open(args.input) as f:
        for line in f:
            line = line.strip()
            if line:
                examples.append(json.loads(line))

    in_scope_tools = _load_in_scope_tools(Path(args.seed_scenarios))
    report = build_coverage_report(examples, in_scope_tools, trace_column=args.trace_column)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    (output_dir / "tool_coverage_report.json").write_text(json.dumps(report, indent=2))
    (output_dir / "tool_coverage_report.md").write_text(render_markdown(report))

    print(f"Analyzed {report['total_examples']} examples.")
    print(f"Tools never called: {len(report['tools_never_called'])} -- {report['tools_never_called']}")
    if report["examples_missing_trace"]:
        print(f"WARNING: {report['examples_missing_trace']} examples had no recognizable trace column.")
    print(f"Report written to {output_dir / 'tool_coverage_report.md'}")


if __name__ == "__main__":
    main()
