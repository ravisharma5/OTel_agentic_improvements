"""Keep going when one checkpoint chunk is filtered to zero rows (2026-10-22).

sdg_hub's ``_process_with_checkpointing`` runs the flow chunk by chunk
(``checkpoint_save_freq`` samples per chunk). If sdg_hub's own quality filters
remove every row of ONE chunk, ``_execute_single_block`` raises
``EmptyDatasetError``. That exception escapes the chunk loop and aborts the
whole attempt. run-generation.py then recovers the rows from earlier chunks'
checkpoints, but every seed in a LATER chunk is never processed in that attempt.

Seen live in fleet run full1_p2/single_P: attempt 1 aborted at chunk 9 of 31,
so about 85 of 121 seeds never ran. Attempts 2 and 3 each aborted on their first
chunk and recovered 0 rows, so 94 scenarios were reported as "never produced a
trajectory" without ever being generated. 446 rows were delivered against 1,970
in full1_p1. Earlier runs lost seeds the same way (full1_p1: 21 such aborts
across 8 processes).

patch_empty_chunk_isolation() wraps ``execute_blocks_on_dataset`` as seen by
``_process_with_checkpointing``: a chunk that raises EmptyDatasetError becomes
an empty DataFrame, so the loop moves on to the next chunk. Empty chunks add
nothing to the checkpoint, and sdg_hub's final concat skips empty frames. If
EVERY chunk is empty, the concat raises FlowValidationError("No valid
datasets..."). That is converted back to EmptyDatasetError, which
run-generation.py already handles (recover from checkpoints, resample).

Only the checkpointed path is patched (the fleet always checkpoints). Set
SDG_EMPTY_CHUNK_ISOLATION=0 to disable. Idempotent. The installed package is
not modified.
"""
from __future__ import annotations

import functools
import logging
import os

logger = logging.getLogger(__name__)
_FLAG = "_sdg_empty_chunk_isolation"
_STATS = {"empty_chunks": 0}


def empty_chunks_skipped() -> int:
    return _STATS["empty_chunks"]


def patch_empty_chunk_isolation() -> None:
    if os.environ.get("SDG_EMPTY_CHUNK_ISOLATION", "1") == "0":
        logger.info("empty-chunk isolation disabled (SDG_EMPTY_CHUNK_ISOLATION=0)")
        return
    import pandas as pd
    from sdg_hub.core.flow import execution
    from sdg_hub.core.utils.error_handling import EmptyDatasetError, FlowValidationError

    if getattr(execution._process_with_checkpointing, _FLAG, False):
        return

    original_execute = execution.execute_blocks_on_dataset
    original_process = execution._process_with_checkpointing

    def _execute_or_empty(flow, chunk_dataset, *args, **kwargs):
        try:
            return original_execute(flow, chunk_dataset, *args, **kwargs)
        except EmptyDatasetError as e:
            _STATS["empty_chunks"] += 1
            logger.warning(
                "Chunk of %d sample(s) was filtered to zero rows (%s) -- skipping this chunk "
                "and continuing with the next one instead of aborting the attempt "
                "(empty chunks so far: %d)",
                len(chunk_dataset), e, _STATS["empty_chunks"],
            )
            return pd.DataFrame()

    @functools.wraps(original_process)
    def _process_with_checkpointing(*args, **kwargs):
        # Swap the module-global lookup only for the duration of this call:
        # _process_with_checkpointing calls execute_blocks_on_dataset by global name.
        execution.execute_blocks_on_dataset = _execute_or_empty
        try:
            return original_process(*args, **kwargs)
        except FlowValidationError as e:
            if "No valid datasets to concatenate" in str(e):
                # every chunk of this attempt was empty: same outcome the caller already handles
                raise EmptyDatasetError("all chunks filtered to zero rows") from e
            raise
        finally:
            execution.execute_blocks_on_dataset = original_execute

    setattr(_process_with_checkpointing, _FLAG, True)
    execution._process_with_checkpointing = _process_with_checkpointing
    logger.info("sdg_hub _process_with_checkpointing patched: empty chunks are skipped, not fatal")
