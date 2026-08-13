"""M2 exit criteria for random schemas, valid instances, and shrinking."""

import json
import re

import pytest
from hypothesis import find, given, settings, strategies as st

from fuzzer.generators.instances import instances, schema_instance_pairs
from fuzzer.generators.schemas import schemas
from fuzzer.oracle.reference import Reference
from fuzzer.oracle.validator import check_schema, validate_text
from fuzzer.shrink import find_minimal


@given(schemas(max_depth=3))
@settings(max_examples=250, deadline=None)
def test_generated_schemas_are_legal(schema):
    result = check_schema(schema)
    assert result, result.reason


@given(data=st.data(), schema=schemas(max_depth=3))
@settings(max_examples=500, deadline=None)
def test_generated_instances_are_valid_compact_json(data, schema):
    instance = data.draw(instances(schema), label="instance")
    result = validate_text(schema, instance)
    assert result, f"{schema!r} generated {instance!r}: {result.reason}"

    in_string = escaped = False
    for char in instance:
        if escaped:
            escaped = False
        elif in_string and char == "\\":
            escaped = True
        elif char == '"':
            in_string = not in_string
        elif not in_string:
            assert char not in " \t\n\r", instance


@given(schema_instance_pairs(max_depth=3))
@settings(max_examples=500, deadline=None)
def test_generated_pairs_are_valid(pair):
    schema, instance = pair
    schema_result = check_schema(schema)
    instance_result = validate_text(schema, instance)
    assert schema_result, schema_result.reason
    assert instance_result, instance_result.reason


def _has_prefix_keys(pair):
    schema, _ = pair
    properties = schema.get("properties", {})
    return "a" in properties and ("ab" in properties or "abc" in properties)


STRESS_PREDICATES = [
    pytest.param(_has_prefix_keys, id="prefix-keys"),
    pytest.param(lambda pair: "\\u" in pair[1], id="escaped-unicode"),
    pytest.param(
        lambda pair: re.search(r"[eE][+-]?[0-9]", pair[1]) is not None,
        id="exponent-number",
    ),
    pytest.param(
        lambda pair: "}}" in pair[1] or "]]" in pair[1] or "}]" in pair[1],
        id="dense-closures",
    ),
]


@pytest.mark.parametrize("predicate", STRESS_PREDICATES)
def test_pair_strategy_reaches_token_boundary_stress_cases(predicate):
    pair = find(
        schema_instance_pairs(max_depth=3),
        predicate,
        settings=settings(
            max_examples=5_000,
            deadline=None,
            database=None,
            derandomize=True,
        ),
    )
    schema, instance = pair
    assert predicate(pair)
    assert check_schema(schema)
    assert validate_text(schema, instance), json.dumps(schema)


def test_synthetic_bug_shrinks_to_a_small_standalone_case():
    def escaped_fixed_string_bug(schema, instance):
        fixed = schema.get("const")
        return (
            isinstance(fixed, str)
            and "\\u" in instance
            and json.loads(instance) == fixed
        )

    case = find_minimal(escaped_fixed_string_bug, max_depth=3, max_examples=5_000)

    assert escaped_fixed_string_bug(case.schema, case.instance)
    assert check_schema(case.schema)
    assert validate_text(case.schema, case.instance)
    assert len(case.reproducer().splitlines()) < 10


@given(schema_instance_pairs(max_depth=3))
@settings(max_examples=10_000, deadline=None, database=None, derandomize=True)
def test_m2_exit_10k_pairs_without_harness_crashes(pair):
    schema, instance = pair
    assert check_schema(schema)
    assert validate_text(schema, instance)

    reference = Reference(schema)
    for cut in range(len(instance) + 1):
        verdict = reference.viable_prefix(instance[:cut])
        assert verdict, (schema, instance, instance[:cut], verdict.reason)
    assert reference.is_complete(instance)
