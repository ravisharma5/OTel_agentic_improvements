"""Tests for OSFT JSONL serialization.

Validates that serialize_single_turn and serialize_multi_turn produce
OSFT-compatible messages arrays with correct tool_call_id threading,
role sequences, and both original and synthetic tool-call IDs.
"""
from __future__ import annotations

import json

import pytest

from sdg.scripts.serialize_osft import (
    row_timeout_count,
    serialize_multi_turn,
    serialize_single_turn,
    tool_result_status,
)


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
    """Calls the agent issued together in one step (shared ``step`` value)."""

    @pytest.fixture()
    def parallel_trace(self) -> dict:
        return {
            "question": "Check alarms and performance",
            "tool_trace": [
                {
                    "name": "tmf642_list_alarms",
                    "input": {"severity": "critical"},
                    "output": {"count": 1},
                    "step": 0,
                },
                {
                    "name": "tmf628_get_performance",
                    "input": {"kpi": "pmRrcConnEstabSucc"},
                    "output": {"value": 99.1},
                    "step": 0,
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

    def test_langchain_wrapped_output_unwraps_to_content(self) -> None:
        """Legacy-Langflow traces carry the full LangChain ToolMessage dict in
        'output' (content, additional_kwargs, response_metadata, artifact,
        tool_call_id, status). Only 'content' -- the real backend response --
        should land in the OSFT tool message, not the transport wrapper."""
        real_payload = '{"areaType":"CIRCLE","center":{"latitude":45.75,"longitude":4.86},"radius":800}'
        trace = {
            "question": "Where is the device with phone number +123456789?",
            "tool_trace": [
                {
                    "name": "camararetrieve_location",
                    "input": {"device_phone_number": "+123456789"},
                    "output": {
                        "content": real_payload,
                        "additional_kwargs": {},
                        "response_metadata": {},
                        "type": "tool",
                        "name": "camararetrieve_location",
                        "id": "ffa2eabc-4213-4dc2-bc66-712a9f558c7a",
                        "tool_call_id": "chatcmpl-tool-9ad0190b1a2abdf5",
                        "artifact": {
                            "structuredContent": {"result": real_payload},
                            "isError": False,
                        },
                        "status": "success",
                    },
                },
            ],
            "answer": "The device is near Lyon, France.",
            "tools": [],
        }
        result = serialize_single_turn(trace)
        tool_messages = [m for m in result["messages"] if m["role"] == "tool"]
        assert len(tool_messages) == 1
        assert tool_messages[0]["content"] == real_payload
        # Transport bookkeeping must not leak into the training content.
        assert "additional_kwargs" not in tool_messages[0]["content"]
        assert "tool_call_id" not in json.loads(tool_messages[0]["content"])

    def test_artifact_structured_content_fallback(self) -> None:
        """When 'content' is absent, fall back to artifact.structuredContent.result."""
        trace = {
            "question": "q",
            "tool_trace": [
                {
                    "name": "fn",
                    "input": {},
                    "output": {
                        "artifact": {"structuredContent": {"result": {"ok": True}}},
                    },
                },
            ],
            "answer": "a",
            "tools": [],
        }
        result = serialize_single_turn(trace)
        tool_messages = [m for m in result["messages"] if m["role"] == "tool"]
        assert json.loads(tool_messages[0]["content"]) == {"ok": True}


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


class TestMainRejectsSchemaInvalidTraces:
    """main() rejects traces whose tool output fails schema validation
    against the tool's documented OpenAPI response, instead of silently
    writing bad data into the OSFT output (the Phase 4 Prism regression)."""

    def test_bad_trace_excluded_good_trace_written(self, tmp_path) -> None:
        from sdg.scripts.serialize_osft import main

        good = {
            "question": "Where is +123456789?",
            "tool_trace": [
                {
                    "name": "camararetrieve_location",
                    "input": {"device_phone_number": "+123456789"},
                    "output": json.dumps(
                        {
                            "lastLocationTime": "2023-10-17T13:18:23.682Z",
                            "area": {
                                "areaType": "CIRCLE",
                                "center": {"latitude": 1.0, "longitude": 2.0},
                                "radius": 1,
                            },
                        }
                    ),
                },
            ],
            "answer": "Near the origin.",
            "tools": [],
        }
        bad = {
            "question": "Where is +199999999?",
            "tool_trace": [
                {
                    "name": "camararetrieve_location",
                    "input": {"device_phone_number": "+199999999"},
                    "output": json.dumps({"area": {"areaType": "CIRCLE", "et_0e_": 1}}),
                },
            ],
            "answer": "Somewhere.",
            "tools": [],
        }
        input_path = tmp_path / "traces.jsonl"
        input_path.write_text(json.dumps(good) + "\n" + json.dumps(bad) + "\n")
        output_dir = tmp_path / "out"

        main(["--input", str(input_path), "--output-dir", str(output_dir), "--format", "single-turn"])

        lines = (output_dir / "single_turn.jsonl").read_text().strip().splitlines()
        assert len(lines) == 1
        written = json.loads(lines[0])
        user_msg = next(m for m in written["messages"] if m["role"] == "user")
        assert user_msg["content"] == "Where is +123456789?"


class TestStepSerialization:
    """SDG-1: each agent step is its own assistant message, followed by that
    step's results, so no call appears to use a result not yet seen."""

    @staticmethod
    def _sequential_trace() -> dict:
        return {
            "question": "Open a ticket for the major alarm",
            "tool_trace": [
                {"name": "tmf642listAlarm", "input": {"perceivedSeverity": "major"},
                 "output": {"content": '[{"id": "8675309"}]'}},
                {"name": "tmf621createTroubleTicket", "input": {"description": "alarm 8675309"},
                 "output": {"content": '{"id": "3180"}'}},
            ],
            "answer": "Opened ticket 3180 for alarm 8675309.",
            "tools": [],
        }

    def test_calls_without_step_are_serialized_one_per_message(self) -> None:
        messages = serialize_single_turn(self._sequential_trace())["messages"]
        roles = [m["role"] for m in messages]
        assert roles == ["system", "user", "assistant", "tool", "assistant", "tool", "assistant"]
        assert [len(m["tool_calls"]) for m in messages if m.get("tool_calls")] == [1, 1]

    def test_dependent_call_comes_after_the_result_it_uses(self) -> None:
        messages = serialize_single_turn(self._sequential_trace())["messages"]
        first_result = next(i for i, m in enumerate(messages) if m["role"] == "tool")
        create_call = next(
            i for i, m in enumerate(messages)
            if any(tc["function"]["name"] == "tmf621createTroubleTicket" for tc in m.get("tool_calls") or [])
        )
        assert "8675309" in messages[first_result]["content"]
        assert create_call > first_result

    def test_mixed_parallel_then_sequential_steps(self) -> None:
        trace = {
            "question": "q",
            "tool_trace": [
                {"name": "a", "input": {}, "output": "ra", "step": 0},
                {"name": "b", "input": {}, "output": "rb", "step": 0},
                {"name": "c", "input": {}, "output": "rc", "step": 1},
            ],
            "answer": "done",
            "tools": [],
        }
        messages = serialize_single_turn(trace)["messages"]
        roles = [m["role"] for m in messages]
        assert roles == ["system", "user", "assistant", "tool", "tool", "assistant", "tool", "assistant"]
        assert [tc["function"]["name"] for tc in messages[2]["tool_calls"]] == ["a", "b"]
        assert [m["content"] for m in messages if m["role"] == "tool"] == ["ra", "rb", "rc"]

    def test_each_result_threads_to_its_own_call(self) -> None:
        messages = serialize_single_turn(self._sequential_trace())["messages"]
        for i, m in enumerate(messages):
            if m["role"] == "tool":
                assert messages[i - 1]["tool_calls"][0]["id"] == m["tool_call_id"]


class TestDeterministicCallIds:
    """SDG-4: the fallback call ID is content-derived, not random."""

    def test_same_trace_serializes_identically(self) -> None:
        trace = TestStepSerialization._sequential_trace()
        assert serialize_single_turn(trace) == serialize_single_turn(trace)

    def test_repeated_identical_calls_get_distinct_ids(self) -> None:
        call = {"name": "tmf642listAlarm", "input": {}, "output": "x"}
        trace = {"question": "q", "tool_trace": [dict(call), dict(call)], "answer": "a", "tools": []}
        ids = [m["tool_call_id"] for m in serialize_single_turn(trace)["messages"] if m["role"] == "tool"]
        assert len(set(ids)) == 2

    def test_ids_unique_across_turns_with_identical_calls(self) -> None:
        turn = {"question": "same", "tool_trace": [{"name": "f", "input": {}, "output": "x"}], "answer": "a"}
        messages = serialize_multi_turn({"turns": [dict(turn), dict(turn)], "tools": []})["messages"]
        ids = [m["tool_call_id"] for m in messages if m["role"] == "tool"]
        assert len(ids) == 2 and len(set(ids)) == 2


class TestToolResultStatus:
    """SDG-3: timed-out tool results are detected from their payload."""

    @pytest.mark.parametrize("content", [
        "Connection to 'r1' (mcp-telecom-basic-r1.c9s.svc.cluster.local) timed out after 30s",
        "Error executing tool show_interfaces: Timed out while waiting for response to ClientRequest. Waited 30.0 seconds.",
        "httpx.ReadTimeout: The read operation timed out",
        "ConnectTimeout",
    ])
    def test_timeouts(self, content: str) -> None:
        assert tool_result_status(content) == "timeout"

    def test_langchain_wrapped_timeout_is_unwrapped(self) -> None:
        assert tool_result_status({"content": "Execution timed out after 120s", "status": "success"}) == "timeout"

    def test_long_payload_mentioning_timeout_is_ok(self) -> None:
        log = "\n".join(f"2026-10-22 bgp neighbor 10.0.0.{i} hold timer expired, session timed out" for i in range(40))
        assert tool_result_status(log) == "ok"

    def test_short_error_is_error_not_timeout(self) -> None:
        assert tool_result_status("Parsing error: Unknown token 'interfaces'.") == "error"
        assert tool_result_status("SNMP support not installed. Run: pip install mcp-telecom[snmp]") == "error"

    def test_normal_payload_is_ok(self) -> None:
        assert tool_result_status('{"result": [{"id": "8675309"}]}') == "ok"

    def test_row_timeout_count_flat_and_multi_turn(self) -> None:
        flat = {"tool_trace": [{"output": "timed out after 30s"}, {"output": "ok"}]}
        multi = {"turns": [{"tool_trace": [{"output": "fine"}]}, {"tool_trace": [{"output": "ReadTimeout"}]}]}
        assert row_timeout_count(flat) == 1
        assert row_timeout_count(multi) == 1
        assert row_timeout_count({"tool_trace": [{"output": "fine"}]}) == 0
