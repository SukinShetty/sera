"""
shared/validators.py — Data validation for SERA.

Before SERA saves, runs, or reports anything, it checks that the data has the
correct structure. This module provides that checking.

Why does this matter?
  Without validation, a typo in a config or a missing field in an experiment
  can cause a confusing crash deep inside the code. With validation, you get
  a clear, plain-English message that tells you exactly what's wrong and where.

There are two main functions:
  - validate_schema() — returns a list of errors (empty = valid)
  - assert_valid()    — raises a ValueError immediately if anything is wrong

Usage:
    from shared.validators import validate_schema, assert_valid

    errors = validate_schema(my_data, my_schema, context="experiment")
    if errors:
        for e in errors:
            print(e)

    # Or stop immediately on error:
    assert_valid(my_data, my_schema, context="hypothesis")
"""

from typing import Any


def validate_schema(data: Any, schema: dict, context: str = "data") -> list:
    """
    Check that 'data' matches the expected 'schema' structure.

    The schema is a plain Python dictionary that describes what is required.
    It supports two kinds of rules:

      1. "required" — list of field names that must be present
         Example: {"required": ["name", "client", "status"]}

      2. "properties" — rules about individual field values
         Each property can have:
           - "type":    expected type — "string", "number", "boolean", "list", "dict"
           - "allowed": list of valid values (like an enum)
         Example: {"properties": {"status": {"allowed": ["draft", "active", "complete"]}}}

    Args:
        data:    The dictionary to validate.
        schema:  The schema dictionary describing the rules.
        context: A label shown in error messages so you know which object failed.

    Returns:
        A list of human-readable error strings.
        An empty list means the data is valid.

    Example:
        schema = {
            "required": ["title", "client", "status"],
            "properties": {
                "status": {"allowed": ["draft", "active", "complete"]},
                "title":  {"type": "string"}
            }
        }
        errors = validate_schema({"title": "Test"}, schema, context="research_note")
        # → ["[research_note] Missing required field: 'client'",
        #     "[research_note] Missing required field: 'status'"]
    """
    errors = []

    # The schema itself must be a dict
    if not isinstance(schema, dict):
        errors.append(
            f"[{context}] Internal error: schema must be a dictionary, "
            f"but got {type(schema).__name__}. This is a SERA code bug."
        )
        return errors

    # The data being validated must be a dict
    if not isinstance(data, dict):
        errors.append(
            f"[{context}] Expected a dictionary (key-value pairs), "
            f"but got {type(data).__name__}."
        )
        return errors

    # --- Rule 1: Check required fields ---
    required_fields = schema.get("required", [])
    for field in required_fields:
        if field not in data:
            errors.append(f"[{context}] Missing required field: '{field}'")

    # --- Rule 2: Check property constraints ---
    properties = schema.get("properties", {})
    for field, rules in properties.items():
        if field not in data:
            continue  # Already reported as missing above if it was required

        value = data[field]

        # Check allowed values (like an enum / dropdown)
        allowed = rules.get("allowed")
        if allowed is not None and value not in allowed:
            errors.append(
                f"[{context}] Field '{field}' has invalid value {value!r}. "
                f"Allowed values are: {allowed}"
            )

        # Check the expected data type
        expected_type = rules.get("type")
        if expected_type:
            _type_map = {
                "string":  str,
                "number":  (int, float),
                "boolean": bool,
                "list":    list,
                "dict":    dict,
            }
            py_type = _type_map.get(expected_type)
            if py_type and not isinstance(value, py_type):
                errors.append(
                    f"[{context}] Field '{field}' should be a {expected_type}, "
                    f"but got {type(value).__name__!r} (value: {value!r})."
                )

    return errors


def assert_valid(data: Any, schema: dict, context: str = "data") -> None:
    """
    Validate 'data' against 'schema' and raise a ValueError if it fails.

    Use this when invalid data should immediately stop execution with a clear,
    readable error message rather than continuing with bad data.

    The error message lists every problem found, numbered, so it's easy to fix
    multiple issues at once.

    Raises:
        ValueError — with a full, numbered list of validation errors.

    Example:
        assert_valid(experiment_data, EXPERIMENT_SCHEMA, context="experiment")
        # If valid: does nothing and continues
        # If invalid: raises ValueError with a readable explanation
    """
    errors = validate_schema(data, schema, context)

    if errors:
        lines = [f"\nValidation failed for '{context}'. Please fix the following:\n"]
        for i, error in enumerate(errors, start=1):
            lines.append(f"  {i}. {error}")
        lines.append("")
        raise ValueError("\n".join(lines))


# --- Pre-built schemas for SERA core objects ---
# Other modules can import and use these directly.

RESEARCH_NOTE_SCHEMA = {
    "required": ["title", "client", "status"],
    "properties": {
        "status": {"allowed": ["draft", "active", "complete", "archived"]},
        "title":  {"type": "string"},
        "client": {"type": "string"},
    }
}

EXPERIMENT_SCHEMA = {
    "required": ["id", "hypothesis", "client", "status"],
    "properties": {
        "status": {"allowed": ["pending", "running", "complete", "failed"]},
        "id":     {"type": "string"},
    }
}

REPORT_SCHEMA = {
    "required": ["client", "title", "format"],
    "properties": {
        "format": {"allowed": ["markdown", "pdf", "html"]},
        "client": {"type": "string"},
        "title":  {"type": "string"},
    }
}
