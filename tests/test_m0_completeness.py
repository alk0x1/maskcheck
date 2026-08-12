"""M0 exit criterion.

One engine (XGrammar), one tokenizer (GPT-2), one hardcoded schema: the canonical
tokenization of a hand-written valid instance is accepted step by step.
"""

import jsonschema
import pytest

from fuzzer.engines.xgrammar import XGrammarAdapter
from fuzzer.properties.completeness import check_completeness
from fuzzer.tokenizers import load_tokenizer

SCHEMA = {
    "type": "object",
    "properties": {"a": {"type": "string"}},
    "required": ["a"],
    "additionalProperties": False,
}
INSTANCE = '{"a":"x"}'
TOKENIZER = "gpt2"


@pytest.fixture(scope="module")
def engine():
    return XGrammarAdapter()


def test_fixture_instance_is_actually_valid():
    """Guard the fixture: a completeness test against an invalid instance proves nothing."""
    jsonschema.validate(INSTANCE and __import__("json").loads(INSTANCE), SCHEMA)


def test_canonical_tokenization_crosses_token_boundaries():
    """Guard the fixture the other way: this instance must exercise boundary-spanning
    tokens, otherwise it is not testing the thing M0 exists to test."""
    tok = load_tokenizer(TOKENIZER)
    pieces = [tok.decode_token(t) for t in tok.encode(INSTANCE)]
    assert pieces == ['{"', "a", '":"', "x", '"}'], pieces


def test_completeness_on_hardcoded_schema(engine):
    result = check_completeness(engine, SCHEMA, INSTANCE, TOKENIZER)
    assert result.violations == [], "\n".join(str(v) for v in result.violations)
    assert result.tokens_checked == 5
