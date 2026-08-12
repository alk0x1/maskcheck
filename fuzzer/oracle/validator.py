"""Reference JSON Schema validation, at the character level.

This is the ground truth for soundness and for certifying oracle witnesses, so it
deliberately does nothing clever: parse the text as JSON, hand it to ``jsonschema``.

Draft 2020-12 is pinned rather than sniffed from ``$schema``. Engines under test each
assume some dialect, and letting the oracle's dialect drift per-schema would turn a
dialect mismatch into a phantom violation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

import jsonschema
from jsonschema.validators import Draft202012Validator

VALIDATOR_CLS = Draft202012Validator
DIALECT = "draft2020-12"


@dataclass(frozen=True)
class ValidationResult:
    valid: bool
    reason: str | None = None

    def __bool__(self) -> bool:
        return self.valid


def check_schema(schema: dict) -> ValidationResult:
    """Whether the schema is itself a legal JSON Schema."""
    try:
        VALIDATOR_CLS.check_schema(schema)
    except jsonschema.SchemaError as exc:
        return ValidationResult(False, f"invalid schema: {exc.message}")
    return ValidationResult(True)


def validate_text(schema: dict, text: str) -> ValidationResult:
    """Whether ``text`` is a JSON document valid against ``schema``.

    Both failure modes are reported the same way on purpose: for a constrained-decoding
    engine, emitting unparseable text and emitting parseable-but-invalid text are the
    same kind of soundness bug.
    """
    try:
        instance = json.loads(text)
    except json.JSONDecodeError as exc:
        return ValidationResult(False, f"not valid JSON: {exc}")
    return validate_instance(schema, instance)


def validate_instance(schema: dict, instance: object) -> ValidationResult:
    try:
        VALIDATOR_CLS(schema).validate(instance)
    except jsonschema.ValidationError as exc:
        path = "/".join(str(p) for p in exc.absolute_path)
        return ValidationResult(False, f"at /{path}: {exc.message}")
    return ValidationResult(True)
