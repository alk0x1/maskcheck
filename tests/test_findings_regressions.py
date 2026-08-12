"""Regression tests pinning every filed finding.

Each test asserts the *current, buggy* behaviour. That is deliberate: when a finding is
fixed upstream, the corresponding test fails loudly and tells us to update the finding
file and the README rather than letting a fixed bug sit in the docs forever.

These duplicate what the standalone reproducers in findings/ assert, on purpose. The
reproducers exist to be pasted into an upstream issue and must not import this harness;
these exist to run in CI.
"""

import json

import jsonschema
import pytest
import xgrammar as xgr

TOKENIZER_INFO = xgr.TokenizerInfo(["a", "b", "c", "d"], vocab_size=4)
COMPILER = xgr.GrammarCompiler(TOKENIZER_INFO)


def accepts(schema, text, **kwargs):
    matcher = xgr.GrammarMatcher(COMPILER.compile_json_schema(schema, **kwargs))
    return matcher.accept_string(text) and matcher.is_completed()


def valid(schema, text):
    return jsonschema.Draft202012Validator(schema).is_valid(json.loads(text))


def obj(props, required=None):
    return {
        "type": "object",
        "properties": props,
        "required": required if required is not None else list(props),
        "additionalProperties": False,
    }


def test_001_negative_zero_unreachable_for_integer():
    schema = {"type": "integer"}
    assert valid(schema, "-0")
    assert not accepts(schema, "-0")
    assert accepts(schema, "0") and accepts(schema, "-1")


@pytest.mark.parametrize("literal", ["1.0", "0.0", "1e2", "-1e2", "0e0"])
def test_002_zero_fractional_part_integers_unreachable(literal):
    schema = {"type": "integer"}
    assert valid(schema, literal), "draft 2020-12 counts these as integers"
    assert not accepts(schema, literal)


@pytest.mark.parametrize("ws,reachable", [(" ", True), ("\t", True), ("\n", True), ("\r", False)])
def test_003_carriage_return_not_treated_as_whitespace(ws, reachable):
    schema = obj({"a": {"type": "string"}})
    text = '{"a":%s"x"}' % ws
    assert valid(schema, text), "all four are RFC 8259 whitespace"
    assert accepts(schema, text) is reachable


def test_003_crlf_pretty_printed_output_is_unreachable():
    schema = obj({"a": {"type": "string"}})
    assert accepts(schema, '{\n  "a": "x"\n}')
    assert not accepts(schema, '{\r\n  "a": "x"\r\n}')


def test_004_only_declaration_order_reachable_by_default():
    import itertools

    schema = obj({k: {"type": "string"} for k in "abc"})
    texts = ["{" + ",".join(f'"{k}":"1"' for k in p) + "}" for p in itertools.permutations("abc")]
    assert all(valid(schema, t) for t in texts)
    assert sum(accepts(schema, t) for t in texts) == 1
    assert sum(accepts(schema, t, any_order=True) for t in texts) == 6


@pytest.mark.parametrize(
    "schema,plain,escaped",
    [
        (obj({"é": {"type": "string"}}), '{"é":"x"}', '{"\\u00e9":"x"}'),
        (obj({"a": {"type": "string"}}), '{"a":"x"}', '{"\\u0061":"x"}'),
        (obj({"v": {"enum": ["alpha"]}}), '{"v":"alpha"}', '{"v":"\\u0061lpha"}'),
        (obj({"v": {"const": "yes"}}), '{"v":"yes"}', '{"v":"\\u0079es"}'),
    ],
    ids=["non-ascii-key", "ascii-key", "enum", "const"],
)
def test_005_escaped_spellings_of_fixed_strings_unreachable(schema, plain, escaped):
    assert json.loads(plain) == json.loads(escaped), "same string, two spellings"
    assert valid(schema, plain) and valid(schema, escaped)
    assert accepts(schema, plain)
    assert not accepts(schema, escaped)


@pytest.mark.parametrize("literal", ["1e1", "2e1", "0.1e2", "100e-1", "1.5e1"])
def test_006_bounds_make_exponent_spellings_unreachable(literal):
    bounded = {"type": "number", "minimum": 10, "maximum": 20}
    assert valid(bounded, literal), "value is in range"
    assert not accepts(bounded, literal)
    assert accepts({"type": "number"}, literal), "reachable without the bound"


@pytest.mark.parametrize("literal", ["9", "21", "1e3", "0.5"])
def test_006_bounds_are_still_enforced_soundly(literal):
    """The counterpart: narrowing the grammar did not open a soundness hole."""
    bounded = {"type": "number", "minimum": 10, "maximum": 20}
    assert not valid(bounded, literal)
    assert not accepts(bounded, literal)
