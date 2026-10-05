---
phase: 04-sdg-pipeline-and-dataset-production
plan: 04
subsystem: sdg-serialization-validation
tags: [osft, jsonl, serializer, validation, tdd, python-package]
dependency_graph:
  requires: []
  provides:
    - sdg-package-structure
    - osft-serializer
    - osft-validation-library
  affects:
    - sdg/scripts/run-evaluation.py (Plan 07 imports osft_validation)
    - sdg/scripts/run-generation.py (uses serializer output)
tech_stack:
  added: []
  patterns:
    - TDD RED/GREEN for both tasks
    - Pure Python stdlib (json, uuid, argparse, pathlib)
    - Package imports via __init__.py (no sys.path manipulation)
key_files:
  created:
    - sdg/__init__.py
    - sdg/scripts/__init__.py
    - sdg/scripts/serialize_osft.py
    - sdg/scripts/test_serialize_osft.py
    - sdg/lib/__init__.py
    - sdg/lib/osft_validation.py
    - sdg/lib/test_osft_validation.py
  modified: []
decisions:
  - "serialize_osft.py uses underscore (not hyphen) for Python importability"
  - "Multi-turn traces use 'turns' key containing list of turn dicts"
  - "System message wraps tool schemas in XML-like <tools> tags per OSFT convention"
  - "osft_validation.py is a pure library (no CLI, no argparse) per amended D-04"
  - "Function arguments validated as JSON strings, not just presence check"
metrics:
  duration: "4m 25s"
  completed: "2026-10-05T22:11:32Z"
  tasks_completed: 2
  tasks_total: 2
  test_count: 46
  files_created: 7
---

# Phase 4 Plan 04: OSFT Serializer and Validation Library Summary

Pure-stdlib OSFT JSONL serializer (single-turn + multi-turn) with tool_call_id threading and a validation library for schema compliance checking, both TDD-built with 46 passing tests

## Task Execution

### Task 1: Package structure + OSFT JSONL serializer and tests

| Step | Commit | Description |
|------|--------|-------------|
| RED | b2c60ae | Failing tests: 6 classes, 23 methods for serializer |
| GREEN | c71e3b6 | Implementation: serialize_single_turn, serialize_multi_turn, CLI |

**Key behaviors implemented:**
- `serialize_single_turn(trace)` produces `[system, user, assistant(tool_calls), tool..., assistant]`
- `serialize_multi_turn(trace)` handles multi-turn traces with shared system message
- Original teacher model `tool_call_id` preserved when `"id"` key present in tool_trace entry
- Synthetic `call_{uuid4.hex[:12]}` generated as fallback
- Parallel tool calls produce multiple tool_calls entries and matching tool messages
- `ValueError` raised for traces with no tool calls
- CLI with `--input`, `--output-dir`, `--format single-turn|multi-turn|both`

### Task 2: OSFT validation library and tests

| Step | Commit | Description |
|------|--------|-------------|
| RED | 44b5cbc | Failing tests: 3 classes, 23 methods for validator |
| GREEN | 7198d0e | Implementation: validate_osft_line, validate_osft_file |

**Key behaviors implemented:**
- `validate_osft_line(line)` checks: messages present/non-empty, valid roles (system/user/assistant/tool), tool_call_id threading, tool_calls structure (id/type/function with name and arguments), valid JSON in function arguments, assistant has content or tool_calls, tool messages have content
- `validate_osft_file(path)` reads JSONL line-by-line with line number tracking, returns `(is_valid, errors_list)` tuple
- Library module with no CLI entry point per amended D-04

## Integration Verification

Serializer output piped into validator: **PASS**

```python
from sdg.scripts.serialize_osft import serialize_single_turn
from sdg.lib.osft_validation import validate_osft_line
trace = {'question': 'test', 'tool_trace': [{'name': 'fn', 'input': {}, 'output': {}}], 'answer': 'done', 'tools': []}
result = serialize_single_turn(trace)
errors = validate_osft_line(result)
assert errors == []  # PASS
```

## Deviations from Plan

None - plan executed exactly as written.

## TDD Gate Compliance

1. RED commit `b2c60ae` (test) exists before GREEN `c71e3b6` (feat) for Task 1
2. RED commit `44b5cbc` (test) exists before GREEN `7198d0e` (feat) for Task 2

All gates satisfied.

## Known Stubs

None. Both modules are fully functional with no placeholder data or TODO markers.

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Multi-turn traces use `turns` key | Differentiates from single-turn `tool_trace` key; enables clear type dispatch |
| System message wraps tools in `<tools>` XML tags | Matches RESEARCH.md Pattern 2 OSFT JSONL format |
| `_make_call_id` helper centralizes ID logic | Single point for original-vs-synthetic ID decision |
| Validation allows conversations without tool_calls | System/user/assistant-only conversations are valid OSFT |

## Self-Check: PASSED

- All 7 created files exist on disk
- All 4 commits (b2c60ae, c71e3b6, 44b5cbc, 7198d0e) verified in git log
- 46 total tests pass (23 serializer + 23 validator)
- Integration check (serializer output -> validator): PASS
