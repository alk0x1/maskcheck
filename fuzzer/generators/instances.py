"""Compact JSON text strategies derived from a supported JSON Schema."""

from __future__ import annotations

import json
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR
from typing import Any

from hypothesis import strategies as st
from hypothesis.strategies import SearchStrategy

STRING_ALPHABET = ("a", "b", "x", "0", '"', "\\", "\n", "\t", "é", "日", "🙂")


def _json_literal(value: Any, ensure_ascii: bool = False) -> str:
    return json.dumps(value, ensure_ascii=ensure_ascii, separators=(",", ":"))


@st.composite
def _fixed_literal(draw, value: Any) -> str:
    if isinstance(value, str):
        ensure_ascii = draw(st.booleans())
        return _json_literal(value, ensure_ascii=ensure_ascii)
    return _json_literal(value)


@st.composite
def _string_instances(draw, schema: dict) -> str:
    minimum = schema.get("minLength", 0)
    maximum = schema.get("maxLength", max(minimum, 12))
    value = draw(
        st.text(
            alphabet=st.sampled_from(STRING_ALPHABET),
            min_size=minimum,
            max_size=maximum,
        )
    )
    return _json_literal(value, ensure_ascii=draw(st.booleans()))


def _integer_instances(schema: dict) -> SearchStrategy[str]:
    minimum = schema.get("minimum")
    maximum = schema.get("maximum")
    lower = (
        int(Decimal(str(minimum)).to_integral_value(rounding=ROUND_CEILING))
        if minimum is not None
        else -1000
    )
    upper = (
        int(Decimal(str(maximum)).to_integral_value(rounding=ROUND_FLOOR))
        if maximum is not None
        else 1000
    )
    if lower > upper:
        return st.nothing()

    def spellings(value: int) -> SearchStrategy[str]:
        variants = [str(value), f"{value}.0", f"{value}e0"]
        if value == 0:
            variants.extend(("-0", "0.0", "0e0"))
        return st.sampled_from(tuple(dict.fromkeys(variants)))

    return st.integers(min_value=lower, max_value=upper).flatmap(spellings)


@st.composite
def _number_instances(draw, schema: dict) -> str:
    minimum = float(schema.get("minimum", -1000))
    maximum = float(schema.get("maximum", 1000))
    if minimum > maximum:
        draw(st.nothing())
    value = draw(
        st.floats(
            min_value=minimum,
            max_value=maximum,
            allow_nan=False,
            allow_infinity=False,
            allow_subnormal=False,
        )
    )
    literal = json.dumps(value)
    variants = [literal]
    if "e" not in literal.lower():
        variants.append(literal + "e0")
    if value == 0:
        variants.extend(("-0", "0.0", "0e0"))
    return draw(st.sampled_from(tuple(dict.fromkeys(variants))))


@st.composite
def _object_instances(draw, schema: dict) -> str:
    properties: dict = schema.get("properties", {})
    required = list(schema.get("required", []))
    optional = [key for key in properties if key not in required]
    included = (
        draw(st.sets(st.sampled_from(optional), max_size=len(optional)))
        if optional
        else set()
    )
    keys = list(dict.fromkeys([*required, *included]))
    order = draw(st.permutations(keys)) if keys else []
    members = []
    for key in order:
        key_text = _json_literal(key, ensure_ascii=draw(st.booleans()))
        value_text = draw(instances(properties.get(key, {})))
        members.append(key_text + ":" + value_text)
    return "{" + ",".join(members) + "}"


@st.composite
def _array_instances(draw, schema: dict) -> str:
    minimum = schema.get("minItems", 0)
    maximum = schema.get("maxItems", max(minimum, 4))
    size = draw(st.integers(min_value=minimum, max_value=maximum))
    values = [draw(instances(schema.get("items", {}))) for _ in range(size)]
    return "[" + ",".join(values) + "]"


def instances(schema: Any) -> SearchStrategy[str]:
    """Compact valid JSON documents for the supported subset of ``schema``."""
    if schema is True or schema == {}:
        return st.sampled_from(("null", "false", "0", '""', "[]", "{}"))
    if schema is False:
        return st.nothing()
    if not isinstance(schema, dict):
        raise TypeError("schema must be a dict or boolean JSON Schema")

    if "const" in schema:
        return _fixed_literal(schema["const"])
    if "enum" in schema:
        return st.sampled_from(tuple(schema["enum"])).flatmap(_fixed_literal)
    if "anyOf" in schema:
        return st.sampled_from(tuple(schema["anyOf"])).flatmap(instances)
    if "oneOf" in schema:
        return st.sampled_from(tuple(schema["oneOf"])).flatmap(instances)

    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        return st.sampled_from(tuple(schema_type)).flatmap(
            lambda chosen: instances({**schema, "type": chosen})
        )
    if schema_type == "string":
        return _string_instances(schema)
    if schema_type == "integer":
        return _integer_instances(schema)
    if schema_type == "number":
        return _number_instances(schema)
    if schema_type == "boolean":
        return st.sampled_from(("true", "false"))
    if schema_type == "null":
        return st.just("null")
    if schema_type == "object":
        return _object_instances(schema)
    if schema_type == "array":
        return _array_instances(schema)
    if schema_type is None:
        return st.sampled_from(("null", "false", "0", '""', "[]", "{}"))
    raise ValueError(f"unsupported generated schema type {schema_type!r}")


def schema_instance_pairs(max_depth: int = 3) -> SearchStrategy[tuple[dict, str]]:
    """Generate a schema and compact valid instance as one shrinkable value."""
    from fuzzer.generators.schemas import schemas

    return schemas(max_depth=max_depth).flatmap(
        lambda schema: instances(schema).map(lambda instance: (schema, instance))
    )
