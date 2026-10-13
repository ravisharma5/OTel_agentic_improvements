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
import json
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
    either a list of output rows or an exception to raise, one per call.

    Records checkpoint_dir/save_freq per call (call_kwargs) so tests can
    verify _run_generation scopes checkpointing per (tier, attempt) rather
    than sharing one directory across the tool-coverage retry loop's
    attempts -- see the comment at _run_generation's _generate_once() call
    site for why a shared directory would be a correctness bug, not just an
    inefficiency.
    """

    def __init__(self, outcomes: list):
        self._outcomes = list(outcomes)
        self.calls = 0
        self.call_kwargs: list[dict] = []

    def generate(self, dataset=None, runtime_params=None, max_concurrency=None,
                 checkpoint_dir=None, save_freq=None):
        self.call_kwargs.append({"checkpoint_dir": checkpoint_dir, "save_freq": save_freq})
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


def test_checkpoint_dir_is_scoped_per_attempt_not_shared(monkeypatch, tmp_path):
    """checkpoint_dir passed to flow.generate() must differ between attempts
    within the same tier, and must be None/disabled when the caller doesn't
    opt in. A shared directory across attempts would let sdg_hub's
    content-based resume matching incorrectly treat attempt 2's resampled
    seeds as already-completed from attempt 1's (inadequate) trajectory."""
    seed = _seed("single_check_alarms")
    fake_flow = _FakeFlow([
        run_generation.EmptyDatasetError("filter_incomplete_responses"),
        [_row("single_check_alarms", ["toolA"])],
    ])
    monkeypatch.setattr(run_generation.Flow, "from_yaml", lambda path: fake_flow)

    checkpoint_base = tmp_path / "checkpoints"
    results = run_generation._run_generation(
        config={"model_config": {}, "agent_config": {}, "runtime_params": {}},
        seeds=[seed],
        output_dir=tmp_path / "out",
        tier_name="single_tool",
        checkpoint_dir=checkpoint_base,
        checkpoint_save_freq=1,
    )

    assert len(results) == 1
    assert fake_flow.calls == 2
    attempt_1_dir = fake_flow.call_kwargs[0]["checkpoint_dir"]
    attempt_2_dir = fake_flow.call_kwargs[1]["checkpoint_dir"]
    assert attempt_1_dir is not None and attempt_2_dir is not None
    assert attempt_1_dir != attempt_2_dir
    assert str(checkpoint_base / "single_tool" / "attempt_1") == attempt_1_dir
    assert str(checkpoint_base / "single_tool" / "attempt_2") == attempt_2_dir
    assert fake_flow.call_kwargs[0]["save_freq"] == 1


def test_empty_dataset_error_recovers_already_checkpointed_chunks(monkeypatch, tmp_path):
    """2026-10-13 live failure: sdg_hub's _process_with_checkpointing has no
    per-chunk exception handling -- when seed 2 of an 11-seed attempt hits
    EmptyDatasetError, the exception propagates immediately, discarding
    seed 1's already-successful, already-checkpointed rows along with it if
    the handler just does `rows = []`. Simulates that exact scenario: a
    checkpoint file exists on disk (written before the failure, as sdg_hub's
    FlowCheckpointer actually does) for a scenario OTHER than the one in
    `remaining` -- the handler must recover it instead of discarding it, and
    the still-failing scenario must still be retried on the next attempt."""
    seed_ok = _seed("single_check_alarms")
    seed_fails = _seed("single_get_nwdaf_analytics")
    checkpoint_base = tmp_path / "checkpoints"
    attempt_1_dir = checkpoint_base / "single_tool" / "attempt_1"
    attempt_1_dir.mkdir(parents=True)
    # Simulate FlowCheckpointer having already saved seed_ok's chunk to disk
    # before seed_fails's chunk raised EmptyDatasetError and killed the call.
    recovered_row = _row("single_check_alarms", ["toolA"])
    (attempt_1_dir / "checkpoint_0001.jsonl").write_text(json.dumps(recovered_row) + "\n")

    fake_flow = _FakeFlow([
        run_generation.EmptyDatasetError("filter_incomplete_responses"),
        [_row("single_get_nwdaf_analytics", ["toolA"])],
    ])
    monkeypatch.setattr(run_generation.Flow, "from_yaml", lambda path: fake_flow)

    results = run_generation._run_generation(
        config={"model_config": {}, "agent_config": {}, "runtime_params": {}},
        seeds=[seed_ok, seed_fails],
        output_dir=tmp_path / "out",
        tier_name="single_tool",
        checkpoint_dir=checkpoint_base,
        checkpoint_save_freq=1,
    )

    scenario_names = {r["scenario_name"] for r in results}
    assert "single_check_alarms" in scenario_names, (
        "seed_ok's already-checkpointed row must be recovered, not discarded, "
        "when a later chunk in the same attempt fails"
    )
    assert "single_get_nwdaf_analytics" in scenario_names, (
        "seed_fails must still be retried and succeed on attempt 2"
    )
    assert fake_flow.calls == 2


def test_checkpoint_dir_disabled_when_not_passed(monkeypatch, tmp_path):
    """Default behavior (no --checkpoint-dir) must be unchanged: None passed
    through to flow.generate(), matching pre-checkpointing behavior exactly."""
    seed = _seed("single_check_alarms")
    fake_flow = _FakeFlow([[_row("single_check_alarms", ["toolA"])]])
    monkeypatch.setattr(run_generation.Flow, "from_yaml", lambda path: fake_flow)

    run_generation._run_generation(
        config={"model_config": {}, "agent_config": {}, "runtime_params": {}},
        seeds=[seed],
        output_dir=tmp_path,
        tier_name="single_tool",
    )

    assert fake_flow.call_kwargs[0] == {"checkpoint_dir": None, "save_freq": None}
