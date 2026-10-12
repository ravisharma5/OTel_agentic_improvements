"""Tests for the tool-coverage rejection-sampling retry loop in
run-generation.py's _run_generation(), including the EmptyDatasetError
handling added after a live failure (04-LEARNINGS.md, 2026-10-09): sdg_hub's
own quality filters can legitimately zero out an entire generation attempt,
and flow.generate() raises EmptyDatasetError rather than returning an empty
result -- the retry loop must treat that as "zero survivors this attempt,"
not crash the whole tier.

Loaded via importlib because the module filename has a hyphen
(run-generation.py), matching this repo's `python -m sdg.scripts.run-generation`
invocation convention.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from unittest import mock

import pytest

_MODULE_PATH = Path(__file__).parent / "run-generation.py"
_spec = importlib.util.spec_from_file_location("sdg.scripts.run_generation_under_test", _MODULE_PATH)
run_generation = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = run_generation
_spec.loader.exec_module(run_generation)  # type: ignore[union-attr]


def _seed(name: str, intended_tools: list[str] | None = None) -> dict:
    return {
        "scenario_name": name,
        "mcp_server_name": name,
        "tier": "single_tool",
        "tool_list": [{"name": t} for t in (intended_tools or ["toolA"])],
        "intended_tools": intended_tools or ["toolA"],
    }


def _row(scenario: str, tools_called: list[str]) -> dict:
    import json

    trace = [
        {"role": "assistant", "tool_calls": [{"id": "1", "function": {"name": t, "arguments": "{}"}}]}
        for t in tools_called
    ]
    return {
        "scenario_name": scenario,
        "mcp_server_name": scenario,
        run_generation.DEFAULT_TRACE_COLUMN: json.dumps(trace),
        "intended_tools": ["toolA"],
    }


class _FakeFlow:
    """Minimal stand-in for sdg_hub's Flow, driven by a scripted sequence of
    either a list of output rows or an exception to raise, one per call."""

    def __init__(self, outcomes: list):
        self._outcomes = list(outcomes)
        self.calls = 0

    def generate(self, dataset=None, runtime_params=None, max_concurrency=None):
        outcome = self._outcomes[self.calls]
        self.calls += 1
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    def set_model_config(self, **kwargs):
        pass

    def set_agent_config(self, **kwargs):
        pass


@pytest.fixture(autouse=True)
def _patch_flow_registry(monkeypatch):
    # _run_generation only checks `FlowRegistry is None or Flow is None` to
    # decide whether to raise ImportError -- give it non-None placeholders.
    monkeypatch.setattr(run_generation, "FlowRegistry", mock.Mock())
    monkeypatch.setattr(run_generation, "Flow", mock.Mock())
    monkeypatch.setattr(run_generation.FlowRegistry, "discover_flows", lambda: None, raising=False)
    monkeypatch.setattr(run_generation.FlowRegistry, "get_flow_path", lambda name: "/dev/null", raising=False)


def test_empty_dataset_error_is_treated_as_zero_survivors_and_retried(monkeypatch, tmp_path):
    """A resample attempt that raises EmptyDatasetError must not crash the
    tier -- it should be treated as zero rows and retried on the next
    attempt, matching the live failure this test guards against."""
    seed = _seed("single_check_alarms")
    fake_flow = _FakeFlow([
        run_generation.EmptyDatasetError("filter_incomplete_responses"),
        [_row("single_check_alarms", ["toolA"])],
    ])
    monkeypatch.setattr(run_generation.Flow, "from_yaml", lambda path: fake_flow)

    results = run_generation._run_generation(
        config={"model_config": {}, "agent_config": {}, "runtime_params": {}},
        seeds=[seed],
        output_dir=tmp_path,
        tier_name="single_tool",
    )

    assert fake_flow.calls == 2
    assert len(results) == 1
    assert results[0]["scenario_name"] == "single_check_alarms"


def test_empty_dataset_error_on_every_attempt_lands_in_coverage_failed(monkeypatch, tmp_path):
    """If every attempt (including the last) raises EmptyDatasetError, the
    scenario must end up excluded from results, not crash the process."""
    seed = _seed("single_check_alarms")
    fake_flow = _FakeFlow([
        run_generation.EmptyDatasetError("filter_incomplete_responses"),
        run_generation.EmptyDatasetError("filter_incomplete_responses"),
        run_generation.EmptyDatasetError("filter_incomplete_responses"),
    ])
    monkeypatch.setattr(run_generation.Flow, "from_yaml", lambda path: fake_flow)

    results = run_generation._run_generation(
        config={"model_config": {}, "agent_config": {}, "runtime_params": {}},
        seeds=[seed],
        output_dir=tmp_path,
        tier_name="single_tool",
    )

    assert fake_flow.calls == 3
    assert results == []
