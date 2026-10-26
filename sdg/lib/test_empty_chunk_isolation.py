"""Tests for empty_chunk_isolation: an all-filtered chunk must not abort later chunks."""
import pandas as pd
import pytest

from sdg.lib import empty_chunk_isolation as eci


class _Checkpointer:
    def __init__(self):
        self.saved = []
        self.final = False

    def add_completed_samples(self, df):
        self.saved.extend(df.to_dict("records"))

    def save_final_checkpoint(self):
        self.final = True


@pytest.fixture
def patched(monkeypatch):
    """Patch with a fake execute_blocks_on_dataset that empties chunks containing 'drop'."""
    from sdg_hub.core.flow import execution
    from sdg_hub.core.utils.error_handling import EmptyDatasetError

    calls = []

    def fake_execute(flow, chunk, runtime_params, flow_logger, max_concurrency, column_tracker):
        calls.append(list(chunk["q"]))
        kept = chunk[~chunk["q"].str.contains("drop")]
        if len(kept) == 0:
            raise EmptyDatasetError("filter_incomplete_responses")
        return kept.assign(a="ok")

    # Start from sdg_hub's stock function even if another test module (run-generation imports)
    # already applied the patch in this session.
    stock = execution._process_with_checkpointing
    stock = getattr(stock, "__wrapped__", stock)
    monkeypatch.setattr(execution, "execute_blocks_on_dataset", fake_execute)
    monkeypatch.setattr(execution, "_process_with_checkpointing", stock)
    eci.patch_empty_chunk_isolation()
    return execution, calls, fake_execute


def _run(execution, rows, save_freq=2):
    import logging
    cp = _Checkpointer()
    out = execution._process_with_checkpointing(
        None, pd.DataFrame({"q": rows}), cp, save_freq, None, {}, logging.getLogger("t"), None, None
    )
    return out, cp


def test_empty_middle_chunk_does_not_stop_later_chunks(patched):
    execution, calls, _ = patched
    out, cp = _run(execution, ["a", "b", "drop1", "drop2", "c", "d"])
    assert calls == [["a", "b"], ["drop1", "drop2"], ["c", "d"]]  # chunk 3 still ran
    assert list(out["q"]) == ["a", "b", "c", "d"]
    assert [r["q"] for r in cp.saved] == ["a", "b", "c", "d"] and cp.final


def test_empty_first_chunk_still_processes_rest(patched):
    execution, calls, _ = patched
    out, _ = _run(execution, ["drop1", "drop2", "x", "y"])
    assert len(calls) == 2 and list(out["q"]) == ["x", "y"]


def test_all_chunks_empty_raises_empty_dataset_error(patched):
    from sdg_hub.core.utils.error_handling import EmptyDatasetError
    execution, calls, _ = patched
    with pytest.raises(EmptyDatasetError):
        _run(execution, ["drop1", "drop2", "drop3"])
    assert len(calls) == 2  # both chunks were attempted


def test_global_restored_after_call(patched):
    execution, _, fake_execute = patched
    _run(execution, ["a", "drop"])
    assert execution.execute_blocks_on_dataset is fake_execute


def test_idempotent(patched):
    execution, _, _ = patched
    first = execution._process_with_checkpointing
    eci.patch_empty_chunk_isolation()
    assert execution._process_with_checkpointing is first


def test_disabled_by_env(monkeypatch):
    from sdg_hub.core.flow import execution
    stock = execution._process_with_checkpointing
    stock = getattr(stock, "__wrapped__", stock)
    monkeypatch.setattr(execution, "_process_with_checkpointing", stock)
    before = execution._process_with_checkpointing
    monkeypatch.setenv("SDG_EMPTY_CHUNK_ISOLATION", "0")
    eci.patch_empty_chunk_isolation()
    assert execution._process_with_checkpointing is before
