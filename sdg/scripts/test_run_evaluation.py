"""Tests for run-evaluation.py's _run_evaluation_flow(), rewritten
2026-10-10 as a pass-through (see its docstring): sdg_hub==0.9.4 has no
"MCP Server Distillation Evaluation" flow and no Flow.evaluate() method at
all -- confirmed live, the first time this stage ran against real production
data. Quality filtering already happens upstream in run-generation.py, so
this stage now just loads and re-writes the raw rows unchanged.

Loaded via importlib because the module filename has a hyphen
(run-evaluation.py), matching this repo's `python -m sdg.scripts.run-evaluation`
invocation convention.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

_MODULE_PATH = Path(__file__).parent / "run-evaluation.py"
_spec = importlib.util.spec_from_file_location("sdg.scripts.run_evaluation_under_test", _MODULE_PATH)
run_evaluation = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = run_evaluation
_spec.loader.exec_module(run_evaluation)  # type: ignore[union-attr]


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    with open(path, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def test_pass_through_preserves_rows_unchanged(tmp_path):
    input_file = tmp_path / "single_tool_raw.jsonl"
    rows = [
        {"question": "q1", "answer": "a1", "tool_trace": [], "tools": []},
        {"question": "q2", "answer": "a2", "tool_trace": [], "tools": []},
    ]
    _write_jsonl(input_file, rows)
    output_dir = tmp_path / "filtered"

    result = run_evaluation._run_evaluation_flow(input_file=input_file, output_dir=output_dir)

    assert result == rows
    written = (output_dir / input_file.name).read_text().strip().splitlines()
    assert [json.loads(line) for line in written] == rows


def test_pass_through_returns_empty_list_for_empty_file(tmp_path):
    input_file = tmp_path / "empty_raw.jsonl"
    input_file.write_text("")
    output_dir = tmp_path / "filtered"

    result = run_evaluation._run_evaluation_flow(input_file=input_file, output_dir=output_dir)

    assert result == []


def test_map_columns_resolves_real_sdg_hub_output_column_names():
    """Regression test for the 2026-10-10 finding: COLUMN_MAP's original
    guessed source names (agent_text, response_text, tool_trace,
    agent_tool_trace) never matched real sdg_hub output -- confirmed live
    the first time a run survived long enough to reach this code path. The
    real columns are extract_agent_text_text (-> answer) and
    DEFAULT_TRACE_COLUMN (-> tool_trace)."""
    row = {
        "question": "What devices are configured?",
        "extract_agent_text_text": "No devices configured.",
        run_evaluation.DEFAULT_TRACE_COLUMN: "[]",
        "tool_list": [{"name": "telecomlist_devices"}],
        "tier": "single_tool",
    }

    mapped = run_evaluation._map_columns(row, 0)

    assert mapped["question"] == "What devices are configured?"
    assert mapped["answer"] == "No devices configured."
    assert mapped["tool_trace"] == []
    assert mapped["tools"] == [{"name": "telecomlist_devices"}]


def _raw_trace(tool_name: str, args: dict, tool_content: str) -> list[dict]:
    """A trace exactly as sdg_hub's Langflow connector emits it."""
    return [
        {"role": "assistant", "content": "", "tool_calls": [
            {"id": "c1", "type": "function", "function": {"name": tool_name, "arguments": json.dumps(args)}}
        ]},
        {"role": "tool", "tool_call_id": "c1", "content": json.dumps(
            {"content": tool_content, "additional_kwargs": {}, "status": "success"}
        )},
    ]


def _raw_row(tool_content: str) -> dict:
    return {
        "question": "List major alarms",
        "extract_agent_text_text": "One major alarm: 8675309.",
        run_evaluation.DEFAULT_TRACE_COLUMN: _raw_trace(
            "tmf642listAlarm", {"perceivedSeverity": "major"}, tool_content
        ),
        "tool_list": [{"name": "tmf642listAlarm"}],
        "tier": "single_tool",
    }


def test_map_columns_normalizes_raw_agent_trace():
    """Regression test for PR #1: without normalization the serializer read
    name/input/output off raw role/tool_calls entries and delivered null
    tool names, empty arguments, and empty results."""
    mapped = run_evaluation._map_columns(_raw_row('[{"id": "8675309"}]'), 0)
    assert mapped["tool_trace"][0]["name"] == "tmf642listAlarm"
    assert mapped["tool_trace"][0]["input"] == {"perceivedSeverity": "major"}

    msgs = run_evaluation.serialize_single_turn(mapped)["messages"]
    call = msgs[2]["tool_calls"][0]["function"]
    assert call["name"] == "tmf642listAlarm"
    assert json.loads(call["arguments"]) == {"perceivedSeverity": "major"}
    assert msgs[3]["content"] == '[{"id": "8675309"}]'


def test_timeout_rows_are_separated_from_delivery(tmp_path):
    good = run_evaluation._map_columns(_raw_row('[{"id": "8675309"}]'), 0)
    timed_out = run_evaluation._map_columns(
        _raw_row("Timed out while waiting for response to ClientRequest. Waited 30.0 seconds."), 1
    )

    stats = run_evaluation._validate_and_serialize([good, timed_out], tmp_path)

    assert stats["total_mapped"] == 2
    assert stats["timeout_rows"] == 1
    assert stats["osft_validated"] == 1
    assert len((tmp_path / "single-turn.jsonl").read_text().splitlines()) == 1
    assert len((tmp_path / run_evaluation.TIMEOUT_ROWS_FILE).read_text().splitlines()) == 1


def test_keep_timeouts_delivers_them(tmp_path):
    timed_out = run_evaluation._map_columns(_raw_row("ReadTimeout"), 0)
    stats = run_evaluation._validate_and_serialize([timed_out], tmp_path, keep_timeouts=True)
    assert stats["timeout_rows"] == 0
    assert stats["osft_validated"] == 1
