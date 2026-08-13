"""Tests for the reference acceptor.

The oracle decides what counts as a bug in someone else's project, so it is tested in
both directions. A reference that answered "viable" to everything would pass the
positive test alone, and one that answered "not viable" to everything would pass the
negative test alone.
"""

import pytest

from fuzzer.corpus import CORPUS, BY_ID
from fuzzer.oracle.reference import Reference, Unsupported

# Prefixes that no valid document can extend, with the reason they are dead.
NON_VIABLE = [
    ("single_string_field", "[", "root must be an object"),
    ("single_string_field", '{"b', "additionalProperties is false"),
    ("single_string_field", '{"a":1', "value must be a string"),
    ("single_string_field", '{"a":"x"}}', "trailing brace"),
    ("single_string_field", '{"a":"x",', "no second property is allowed"),
    ("single_string_field", "{}", "property a is required"),
    ("enum_shared_prefix", '{"v":"alq', "no enum member starts with alq"),
    ("enum_shared_prefix", '{"v":"alphabetic"', "closed short of any member"),
    ("integers", '{"n":"', "value must be an integer"),
    ("integers", '{"n":01', "leading zeros are not legal JSON"),
    ("bounded_number", '{"n":5}', "below minimum 10"),
    ("array_of_strings", '{"a":[1', "items must be strings"),
    ("nested_objects", '{"a":{"b":"', "b must be an object"),
    ("string_escapes", '{"s":"\\q', "invalid escape sequence"),
    ("booleans_and_null", '{"a":nul', "a must be a boolean, not null"),
]

# Prefixes that look dead but are not. Each one caught a wrong expectation of mine
# while writing these tests, which is exactly why the witness is checked.
SURPRISING_BUT_VIABLE = [
    # 1.5e1 is 15.0, an integer under the draft 6+ "zero fractional part" rule.
    ("integers", '{"n":1.5', "1.5e1 has a zero fractional part"),
    # "a is already used, but the partial key can still open "ab" or "abc".
    ("prefix_keys", '{"a":"x","a', "can still become ab or abc"),
]


@pytest.mark.parametrize("case", CORPUS, ids=lambda c: c.id)
def test_every_prefix_of_a_valid_instance_is_viable(case):
    """The reference must never call a prefix of a valid document a dead end.

    False negatives here would become phantom violations reported against engines.
    """
    reference = Reference(case.schema)
    for instance in case.instances:
        for cut in range(len(instance) + 1):
            prefix = instance[:cut]
            assert reference.viable_prefix(prefix), (
                f"{prefix!r} is a prefix of the valid instance {instance!r} "
                f"but the reference judged it non-viable"
            )


@pytest.mark.parametrize("case", CORPUS, ids=lambda c: c.id)
def test_valid_instances_are_complete(case):
    reference = Reference(case.schema)
    for instance in case.instances:
        assert reference.is_complete(instance)


@pytest.mark.parametrize(
    "case_id,prefix,reason", NON_VIABLE, ids=[f"{c}:{p}" for c, p, _ in NON_VIABLE]
)
def test_dead_prefixes_are_rejected(case_id, prefix, reason):
    verdict = Reference(BY_ID[case_id].schema).viable_prefix(prefix)
    assert not verdict, f"expected non-viable ({reason}); got witness {verdict.witness!r}"


@pytest.mark.parametrize(
    "case_id,prefix,reason",
    SURPRISING_BUT_VIABLE,
    ids=[f"{c}:{p}" for c, p, _ in SURPRISING_BUT_VIABLE],
)
def test_surprising_prefixes_are_viable_with_a_witness(case_id, prefix, reason):
    verdict = Reference(BY_ID[case_id].schema).viable_prefix(prefix)
    assert verdict, f"expected viable ({reason})"
    assert verdict.witness.startswith(prefix)


def test_positive_verdicts_carry_a_validated_witness():
    reference = Reference(BY_ID["single_string_field"].schema)
    verdict = reference.viable_prefix('{"a":')
    assert verdict.witness == '{"a":""}'
    assert reference.is_complete(verdict.witness)


@pytest.mark.parametrize(
    "prefix,expected",
    [
        ('{"n":0', True),
        ('{"n":1', True),
        ('{"n":1.', True),
        ('{"n":1e', True),
        ('{"n":3', False),
        ('{"n":30', False),
        ('{"n":1e-', False),
    ],
)
def test_bounded_number_prefixes_are_decided_arithmetically(prefix, expected):
    """Numeric bounds are decided without a bounded character search."""
    reference = Reference(BY_ID["bounded_number"].schema)
    verdict = reference.viable_prefix(prefix)
    assert bool(verdict) is expected
    if verdict:
        assert verdict.witness.startswith(prefix)
        assert reference.is_complete(verdict.witness)


@pytest.mark.parametrize(
    "schema,prefix,expected",
    [
        ({"type": "integer", "minimum": -20, "maximum": -10}, "-", True),
        ({"type": "integer", "minimum": -20, "maximum": -10}, "-0", True),
        ({"type": "integer", "minimum": -20, "maximum": -10}, "-10.", True),
        ({"type": "integer", "minimum": -20, "maximum": -10}, "-3", False),
        ({"type": "integer", "maximum": -1.8}, "-1", True),
        ({"type": "integer", "minimum": 0, "maximum": 0}, "1", False),
        ({"type": "number", "minimum": 1.25, "maximum": 1.5}, "1.2", True),
        ({"type": "number", "minimum": 1.25, "maximum": 1.5}, "1.6", False),
        ({"type": "integer", "minimum": 10, "maximum": 20}, "1e+", True),
        ({"type": "integer", "minimum": 10, "maximum": 20}, "1e0", True),
        ({"type": "integer", "minimum": 10, "maximum": 20}, "1e2", False),
        ({"type": "integer", "minimum": 10, "maximum": 20}, "100e-", True),
    ],
)
def test_bounded_number_arithmetic_handles_sign_fraction_and_exponent(
    schema, prefix, expected
):
    reference = Reference(schema)
    verdict = reference.viable_prefix(prefix)
    assert bool(verdict) is expected
    if verdict:
        assert verdict.witness.startswith(prefix)
        assert reference.is_complete(verdict.witness)


def test_fractional_minimum_builds_an_integer_witness_for_an_empty_prefix():
    reference = Reference({"type": "integer", "minimum": -1.5, "maximum": 1.5})
    verdict = reference.viable_prefix("")
    assert verdict.witness == "0"
    assert reference.is_complete(verdict.witness)


@pytest.mark.parametrize(
    "schema,expected",
    [
        ({"type": "integer", "maximum": -10}, "-10"),
        ({"type": "number", "maximum": -10.5}, "-10.5"),
    ],
)
def test_negative_maximum_builds_a_numeric_witness_for_an_empty_prefix(
    schema, expected
):
    reference = Reference(schema)
    verdict = reference.viable_prefix("")
    assert verdict.witness == expected
    assert reference.is_complete(verdict.witness)


def test_unbounded_numbers_stay_decidable():
    """The abstention above must not leak into ordinary numeric schemas."""
    reference = Reference(BY_ID["integers"].schema)
    assert reference.viable_prefix('{"n":30')
    assert reference.viable_prefix('{"n":-')
    assert not reference.viable_prefix('{"n":01')


def test_unsupported_constructs_abstain_rather_than_guess():
    """A construct the parser cannot model must raise, never answer "not viable"."""
    with pytest.raises(Unsupported):
        Reference({"type": "string", "pattern": "^a+$"})
    with pytest.raises(Unsupported):
        Reference({"allOf": [{"type": "string"}]})


def test_surrounding_whitespace_is_configurable():
    """The default follows the engines; the RFC reading is still available."""
    schema = BY_ID["single_string_field"].schema
    assert not Reference(schema).viable_prefix(" ")
    assert Reference(schema, allow_surrounding_whitespace=True).viable_prefix(" ")


def test_interior_whitespace_is_always_viable():
    """This is the check that surfaced the carriage-return finding."""
    reference = Reference(BY_ID["single_string_field"].schema)
    for ws in [" ", "\t", "\n", "\r"]:
        assert reference.viable_prefix('{"a":' + ws), f"{ws!r} is RFC 8259 whitespace"


def test_prefix_inside_a_unicode_surrogate_pair_remains_viable():
    schema = {"type": "string", "minLength": 4}
    prefix = r'"00\ud83d\ude'
    verdict = Reference(schema).viable_prefix(prefix)
    assert verdict
    assert verdict.witness.startswith(prefix)
    assert Reference(schema).is_complete(verdict.witness)
