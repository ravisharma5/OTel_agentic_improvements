"""OSFT schema compliance validation library.

Provides validate_osft_line and validate_osft_file for checking OSFT
JSONL format compliance including tool_call_id threading, required
fields, and valid JSON function arguments.

Also provides validate_tool_output_against_schema, a separate check that a
tool's *content* -- not just the OSFT envelope around it -- actually
conforms to the tool's documented OpenAPI response schema. Added after
Phase 4 found Prism's dynamic mock mode fabricating wrong response
*structure* (garbled property names, missing required objects, flipped
discriminator types) for schemas with oneOf/discriminator polymorphism --
syntactically valid JSON that was still a lie about the API contract.
validate_osft_line/validate_osft_file would not catch this: they validate
the envelope (roles, tool_call_id threading), not whether tool content is
true to the tool it claims to come from. Execution-verified SDG is only
meaningful if this also holds, so run it before accepting a trajectory.

Per amended D-04, these functions are imported by run-evaluation.py
(Plan 07) and called automatically after the eval flow completes --
this is a library module, not a standalone script.
"""
from __future__ import annotations

import json
from pathlib import Path

import yaml
from jsonschema import RefResolver
from jsonschema import ValidationError as _JsonSchemaValidationError
from jsonschema import validate as _jsonschema_validate

_VALID_ROLES = {"system", "user", "assistant", "tool"}

# Maps MCP tool name -> (spec file relative to repo root, schema name under
# components.schemas) for the tool's *response* body. Only tools that have
# been verified end-to-end against a live call are listed here -- do not
# guess a mapping for an unverified tool; add it once you've confirmed the
# real response shape, the same way camararetrieve_location was confirmed
# during Phase 4 (see docs/blog-sdg-pipeline-learnings.md).
TOOL_RESPONSE_SCHEMAS: dict[str, tuple[str, str]] = {
    "camararetrieve_location": ("mcp/camara/specs/camara_location_retrieval.yaml", "Location"),
}


def validate_tool_output_against_schema(
    tool_name: str,
    output_content: str,
    *,
    repo_root: Path | None = None,
    schema_map: dict[str, tuple[str, str]] | None = None,
) -> list[str]:
    """Validate a tool's output JSON against its documented OpenAPI response schema.

    Args:
        tool_name: MCP tool name as it appears in a tool_trace entry's 'name'.
        output_content: The tool's response payload -- a JSON string (e.g.
            the already-unwrapped value from serialize_osft's
            _extract_tool_output_content, not the raw LangChain ToolMessage).
        repo_root: Repo root to resolve spec paths from. Defaults to the
            directory three levels up from this file (sdg/lib/ -> repo root).
        schema_map: Overrides TOOL_RESPONSE_SCHEMAS, mainly for tests.

    Returns:
        List of error strings. Empty list means either valid, or no schema
        is registered for this tool yet (unmapped tools are not rejected --
        only checked when a mapping exists).
    """
    schema_map = schema_map if schema_map is not None else TOOL_RESPONSE_SCHEMAS
    if tool_name not in schema_map:
        return []

    repo_root = repo_root or Path(__file__).resolve().parents[2]
    spec_rel_path, schema_name = schema_map[tool_name]
    spec_path = repo_root / spec_rel_path

    try:
        instance = json.loads(output_content)
    except (json.JSONDecodeError, TypeError) as exc:
        return [f"{tool_name}: output is not valid JSON: {exc}"]

    try:
        spec_doc = yaml.safe_load(spec_path.read_text())
    except OSError as exc:
        return [f"{tool_name}: could not read spec {spec_path}: {exc}"]

    schema = {"$ref": f"#/components/schemas/{schema_name}"}
    resolver = RefResolver.from_schema(spec_doc)

    try:
        _jsonschema_validate(instance=instance, schema=schema, resolver=resolver)
    except _JsonSchemaValidationError as exc:
        path = "/".join(str(p) for p in exc.absolute_path) or "<root>"
        return [f"{tool_name}: response does not match '{schema_name}' schema at {path}: {exc.message}"]

    return []


def validate_tool_trace_outputs(
    tool_trace: list[dict],
    *,
    repo_root: Path | None = None,
    schema_map: dict[str, tuple[str, str]] | None = None,
) -> list[str]:
    """Validate every tool call's output in a trace against its response schema.

    Args:
        tool_trace: List of {"name", "input", "output"} dicts, where
            'output' is already the unwrapped payload (string or dict) --
            run this after serialize_osft's output extraction, not on the
            raw agent-framework trace.

    Returns:
        List of error strings across all entries. Empty list means every
        mapped tool's output validated clean (unmapped tools are skipped).
    """
    errors: list[str] = []
    for entry in tool_trace:
        name = entry.get("name", "")
        output = entry.get("output", "")
        content = output if isinstance(output, str) else json.dumps(output)
        errors.extend(
            validate_tool_output_against_schema(
                name, content, repo_root=repo_root, schema_map=schema_map
            )
        )
    return errors


def validate_osft_line(line: dict) -> list[str]:
    """Validate a single OSFT JSONL line for schema compliance.

    Checks:
        - ``messages`` key exists and is a non-empty list
        - Every message has a valid ``role``
        - Tool messages have ``tool_call_id`` matching a prior assistant
          ``tool_calls[].id``
        - Tool messages have ``content``
        - Assistant messages with ``tool_calls`` have properly structured
          entries (id, type, function with name and arguments)
        - Function ``arguments`` is a valid JSON string
        - Assistant messages have either ``content`` or ``tool_calls``

    Args:
        line: A single parsed OSFT JSONL record (dict).

    Returns:
        List of error description strings. Empty list means valid.
    """
    errors: list[str] = []

    # --- messages key ---
    if "messages" not in line:
        errors.append("Missing 'messages' key")
        return errors

    messages = line["messages"]
    if not isinstance(messages, list):
        errors.append("'messages' must be a list")
        return errors

    if len(messages) == 0:
        errors.append("'messages' is empty")
        return errors

    # Collect all tool_call IDs from assistant messages for cross-reference
    all_tool_call_ids: set[str] = set()

    for idx, msg in enumerate(messages):
        prefix = f"Message {idx}"

        # --- role ---
        if "role" not in msg:
            errors.append(f"{prefix}: missing 'role'")
            continue

        role = msg["role"]
        if role not in _VALID_ROLES:
            errors.append(
                f"{prefix}: invalid role '{role}' "
                f"(must be one of {sorted(_VALID_ROLES)})"
            )
            continue

        # --- assistant messages ---
        if role == "assistant":
            has_content = "content" in msg and msg["content"] is not None
            has_tool_calls = "tool_calls" in msg and msg["tool_calls"]

            if not has_content and not has_tool_calls:
                errors.append(
                    f"{prefix}: assistant message must have 'content' "
                    f"or non-empty 'tool_calls'"
                )

            if has_tool_calls:
                for tc_idx, tc in enumerate(msg["tool_calls"]):
                    tc_prefix = f"{prefix}, tool_calls[{tc_idx}]"

                    if "id" not in tc:
                        errors.append(f"{tc_prefix}: missing 'id'")
                    else:
                        all_tool_call_ids.add(tc["id"])

                    if "type" not in tc:
                        errors.append(f"{tc_prefix}: missing 'type'")

                    if "function" not in tc:
                        errors.append(f"{tc_prefix}: missing 'function'")
                    else:
                        fn = tc["function"]
                        if "name" not in fn:
                            errors.append(
                                f"{tc_prefix}: function missing 'name'"
                            )
                        if "arguments" not in fn:
                            errors.append(
                                f"{tc_prefix}: function missing 'arguments'"
                            )
                        elif isinstance(fn["arguments"], str):
                            try:
                                json.loads(fn["arguments"])
                            except (json.JSONDecodeError, ValueError):
                                errors.append(
                                    f"{tc_prefix}: function 'arguments' "
                                    f"is not valid JSON"
                                )

        # --- tool messages ---
        elif role == "tool":
            if "tool_call_id" not in msg:
                errors.append(f"{prefix}: tool message missing 'tool_call_id'")
            elif msg["tool_call_id"] not in all_tool_call_ids:
                errors.append(
                    f"{prefix}: tool_call_id '{msg['tool_call_id']}' "
                    f"has no matching tool_calls[].id in a prior "
                    f"assistant message"
                )

            if "content" not in msg:
                errors.append(f"{prefix}: tool message missing 'content'")

    return errors


def validate_osft_file(path: str) -> tuple[bool, list[str]]:
    """Validate an OSFT JSONL file for schema compliance.

    Reads the file line by line, parses each as JSON, and runs
    ``validate_osft_line`` on each parsed record. Collects errors
    with line numbers.

    Args:
        path: Path to the JSONL file.

    Returns:
        Tuple of (is_valid, errors_list). ``is_valid`` is True when
        all lines pass validation. ``errors_list`` contains error
        strings prefixed with line numbers.
    """
    all_errors: list[str] = []
    filepath = Path(path)

    with filepath.open() as f:
        for line_no, raw_line in enumerate(f, start=1):
            raw_line = raw_line.strip()
            if not raw_line:
                continue

            try:
                parsed = json.loads(raw_line)
            except (json.JSONDecodeError, ValueError) as exc:
                all_errors.append(
                    f"Line {line_no}: JSON parse error: {exc}"
                )
                continue

            line_errors = validate_osft_line(parsed)
            for err in line_errors:
                all_errors.append(f"Line {line_no}: {err}")

    return (len(all_errors) == 0, all_errors)
