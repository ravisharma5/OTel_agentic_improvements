"""Tests for OSFT JSONL serialization.

Validates that serialize_single_turn and serialize_multi_turn produce
OSFT-compatible messages arrays with correct tool_call_id threading,
role sequences, and both original and synthetic tool-call IDs.
"""
from __future__ import annotations

import json

import pytest

from sdg.scripts.serialize_osft import serialize_multi_turn, serialize_single_turn


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


class TestSingleTurnSerialization:
    """Single-turn traces produce the expected 5-message sequence."""

    @pytest.fixture()
    def single_tool_trace(self) -> dict:
        """Trace with one tool call -- NO 'id' key, triggers synthetic UUID."""
        return {
            "question": "Are there critical alarms on the network?",
            "tool_trace": [
                {
                    "name": "tmf642_list_alarms",
                    "input": {"severity": "critical"},
                    "output": {
                        "id": "8675309",
                        "alarmType": "environmentalAlarm",
                        "perceivedSeverity": "critical",
                    },
                },
            ],
            "answer": "Found one critical alarm (ID: 8675309).",
            "tools": [
                {
                    "type": "function",
                    "function": {
                        "name": "tmf642_list_alarms",
                        "description": "List or find Alarm objects",
                        "parameters": {
                            "type": "object",
                            "properties": {
                                "severity": {
                                    "type": "string",
                                    "enum": [
                                        "critical",
                                        "major",
                                        "minor",
                                        "warning",
                                        "indeterminate",
                                    ],
                                },
                            },
                        },
                    },
                },
            ],
        }

    def test_produces_valid_messages(self, single_tool_trace: dict) -> None:
        result = serialize_single_turn(single_tool_trace)
        assert "messages" in result
        messages = result["messages"]
        # system, user, assistant(tool_calls), tool, assistant
        assert len(messages) == 5

    def test_tool_call_id_threading(self, single_tool_trace: dict) -> None:
        messages = serialize_single_turn(single_tool_trace)["messages"]
        assistant_call_id = messages[2]["tool_calls"][0]["id"]
        tool_response_id = messages[3]["tool_call_id"]
        assert assistant_call_id == tool_response_id

    def test_system_message_contains_tools(self, single_tool_trace: dict) -> None:
        messages = serialize_single_turn(single_tool_trace)["messages"]
        assert messages[0]["role"] == "system"
        assert "tmf642_list_alarms" in messages[0]["content"]

    def test_assistant_tool_calls_structure(self, single_tool_trace: dict) -> None:
        messages = serialize_single_turn(single_tool_trace)["messages"]
        assistant = messages[2]
        assert assistant["content"] is None
        tc = assistant["tool_calls"][0]
        assert "id" in tc
        assert tc["type"] == "function"
        assert "name" in tc["function"]
        assert "arguments" in tc["function"]

    def test_synthetic_id_when_no_original(self, single_tool_trace: dict) -> None:
        """When tool_trace entry has no 'id' key, a synthetic call_ ID is used."""
        messages = serialize_single_turn(single_tool_trace)["messages"]
        call_id = messages[2]["tool_calls"][0]["id"]
        assert call_id.startswith("call_")

    def test_role_sequence(self, single_tool_trace: dict) -> None:
        messages = serialize_single_turn(single_tool_trace)["messages"]
        roles = [m["role"] for m in messages]
        assert roles == ["system", "user", "assistant", "tool", "assistant"]

    def test_function_arguments_is_json_string(self, single_tool_trace: dict) -> None:
        messages = serialize_single_turn(single_tool_trace)["messages"]
        args = messages[2]["tool_calls"][0]["function"]["arguments"]
        assert isinstance(args, str)
        parsed = json.loads(args)
        assert parsed == {"severity": "critical"}

    def test_tool_response_content_is_json_string(
        self, single_tool_trace: dict
    ) -> None:
        messages = serialize_single_turn(single_tool_trace)["messages"]
        content = messages[3]["content"]
        assert isinstance(content, str)
        parsed = json.loads(content)
        assert parsed["id"] == "8675309"

    def test_final_assistant_has_answer(self, single_tool_trace: dict) -> None:
        messages = serialize_single_turn(single_tool_trace)["messages"]
        assert messages[4]["role"] == "assistant"
        assert messages[4]["content"] == "Found one critical alarm (ID: 8675309)."


class TestOriginalToolCallIdPreservation:
    """When the tool_trace entry has an 'id' key, it is preserved as-is."""

    @pytest.fixture()
    def trace_with_original_id(self) -> dict:
        return {
            "question": "Check alarms",
            "tool_trace": [
                {
                    "id": "call_abc123def456",
                    "name": "tmf642_list_alarms",
                    "input": {"severity": "major"},
                    "output": {"id": "42", "perceivedSeverity": "major"},
                },
            ],
            "answer": "One major alarm found.",
            "tools": [],
        }

    def test_preserves_original_id(self, trace_with_original_id: dict) -> None:
        messages = serialize_single_turn(trace_with_original_id)["messages"]
        assert messages[2]["tool_calls"][0]["id"] == "call_abc123def456"

    def test_tool_message_uses_original_id(
        self, trace_with_original_id: dict
    ) -> None:
        messages = serialize_single_turn(trace_with_original_id)["messages"]
        assert messages[3]["tool_call_id"] == "call_abc123def456"


class TestMultiTurnSerialization:
    """Multi-turn traces produce multiple user/assistant/tool rounds."""

    @pytest.fixture()
    def multi_turn_trace(self) -> dict:
        return {
            "turns": [
                {
                    "question": "List critical alarms",
                    "tool_trace": [
                        {
                            "name": "tmf642_list_alarms",
                            "input": {"severity": "critical"},
                            "output": {"count": 2},
                        },
                    ],
                    "answer": "Found 2 critical alarms.",
                },
                {
                    "question": "Get performance metrics",
                    "tool_trace": [
                        {
                            "name": "tmf628_get_performance",
                            "input": {"kpi": "pmActiveUEDlMean"},
                            "output": {"value": 42.5},
                        },
                    ],
                    "answer": "Average DL UE count is 42.5.",
                },
            ],
            "tools": [],
        }

    def test_multi_turn_has_multiple_user_messages(
        self, multi_turn_trace: dict
    ) -> None:
        messages = serialize_multi_turn(multi_turn_trace)["messages"]
        user_count = sum(1 for m in messages if m["role"] == "user")
        assert user_count == 2

    def test_multi_turn_preserves_order(self, multi_turn_trace: dict) -> None:
        messages = serialize_multi_turn(multi_turn_trace)["messages"]
        roles = [m["role"] for m in messages]
        # system, then for each turn: user, assistant(tool_calls), tool, assistant
        assert roles[0] == "system"
        # Turn 1
        assert roles[1] == "user"
        assert roles[2] == "assistant"
        assert roles[3] == "tool"
        assert roles[4] == "assistant"
        # Turn 2
        assert roles[5] == "user"
        assert roles[6] == "assistant"
        assert roles[7] == "tool"
        assert roles[8] == "assistant"

    def test_multi_turn_tool_call_id_threading_per_turn(
        self, multi_turn_trace: dict
    ) -> None:
        messages = serialize_multi_turn(multi_turn_trace)["messages"]
        # Turn 1: messages[2] assistant, messages[3] tool
        assert messages[2]["tool_calls"][0]["id"] == messages[3]["tool_call_id"]
        # Turn 2: messages[6] assistant, messages[7] tool
        assert messages[6]["tool_calls"][0]["id"] == messages[7]["tool_call_id"]


class TestParallelToolCalls:
    """Traces with multiple tool calls in one turn."""

    @pytest.fixture()
    def parallel_trace(self) -> dict:
        return {
            "question": "Check alarms and performance",
            "tool_trace": [
                {
                    "name": "tmf642_list_alarms",
                    "input": {"severity": "critical"},
                    "output": {"count": 1},
                },
                {
                    "name": "tmf628_get_performance",
                    "input": {"kpi": "pmRrcConnEstabSucc"},
                    "output": {"value": 99.1},
                },
            ],
            "answer": "1 critical alarm, RRC success rate 99.1%.",
            "tools": [],
        }

    def test_parallel_produces_two_tool_messages(self, parallel_trace: dict) -> None:
        messages = serialize_single_turn(parallel_trace)["messages"]
        tool_msgs = [m for m in messages if m["role"] == "tool"]
        assert len(tool_msgs) == 2

    def test_parallel_message_structure(self, parallel_trace: dict) -> None:
        messages = serialize_single_turn(parallel_trace)["messages"]
        # system, user, assistant(2 tool_calls), tool, tool, assistant
        assert len(messages) == 6
        roles = [m["role"] for m in messages]
        assert roles == ["system", "user", "assistant", "tool", "tool", "assistant"]

    def test_parallel_tool_call_ids_unique(self, parallel_trace: dict) -> None:
        messages = serialize_single_turn(parallel_trace)["messages"]
        tc_ids = [tc["id"] for tc in messages[2]["tool_calls"]]
        assert len(set(tc_ids)) == 2  # Both IDs are unique

    def test_parallel_tool_call_id_threading(self, parallel_trace: dict) -> None:
        messages = serialize_single_turn(parallel_trace)["messages"]
        for i, tc in enumerate(messages[2]["tool_calls"]):
            assert tc["id"] == messages[3 + i]["tool_call_id"]


class TestEdgeCases:
    """Edge case handling."""

    def test_no_tool_calls_raises(self) -> None:
        trace = {
            "question": "Hello",
            "tool_trace": [],
            "answer": "Hi",
            "tools": [],
        }
        with pytest.raises(ValueError, match="no tool calls"):
            serialize_single_turn(trace)

    def test_no_tool_trace_key_raises(self) -> None:
        trace = {"question": "Hello", "answer": "Hi", "tools": []}
        with pytest.raises(ValueError, match="no tool calls"):
            serialize_single_turn(trace)

    def test_empty_answer_still_serializes(self) -> None:
        trace = {
            "question": "Do something",
            "tool_trace": [
                {"name": "fn", "input": {}, "output": {}},
            ],
            "answer": "",
            "tools": [],
        }
        result = serialize_single_turn(trace)
        messages = result["messages"]
        assert messages[-1]["role"] == "assistant"
        assert messages[-1]["content"] == ""


class TestCLIArguments:
    """CLI mode argument parsing."""

    def test_cli_parser_exists(self) -> None:
        from sdg.scripts.serialize_osft import build_parser

        parser = build_parser()
        args = parser.parse_args(
            ["--input", "traces.jsonl", "--output-dir", "out", "--format", "both"]
        )
        assert args.input == "traces.jsonl"
        assert args.output_dir == "out"
        assert args.format == "both"

    def test_cli_format_choices(self) -> None:
        from sdg.scripts.serialize_osft import build_parser

        parser = build_parser()
        for fmt in ("single-turn", "multi-turn", "both"):
            args = parser.parse_args(
                ["--input", "t.jsonl", "--output-dir", "o", "--format", fmt]
            )
            assert args.format == fmt
