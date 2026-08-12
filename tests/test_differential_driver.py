"""Tests for the differential driver itself.

Every violation found against XGrammar so far has been a completeness violation, which
means the soundness direction of this driver has never fired on real data. A driver
that cannot detect a soundness violation would report zero of them forever and look
exactly like a clean result. So it is exercised here against mock engines whose bugs
are known by construction.
"""

import pytest

from fuzzer.corpus import BY_ID
from fuzzer.properties.differential import check_differential
from fuzzer.tokenizers import load_tokenizer

TOKENIZER = "gpt2"
CASE = BY_ID["single_string_field"]


@pytest.fixture(scope="module")
def candidates():
    """A small, fixed token subset: the driver is exact but a full scan is slow."""
    tok = load_tokenizer(TOKENIZER)
    ids = set(tok.encode(CASE.instances[0]))
    for text in ['{"', "a", '":"', "x", '"}', "b", "1", "[", "}", ",", " "]:
        ids.update(tok.encode(text))
    return sorted(ids)


class _Matcher:
    def __init__(self, allowed, vocab_size):
        self._allowed = allowed
        self._vocab = vocab_size

    def allowed_mask(self):
        return self._allowed

    def accept(self, token_id):
        return True

    def is_completed(self):
        return True

    def is_terminated(self):
        return False

    def can_stop(self):
        return True

    def reset(self):
        pass


class AllowEverything:
    """Maximally unsound: every token is legal in every state."""

    name = "mock-allow-everything"

    def compile(self, schema, tokenizer_id):
        vocab = load_tokenizer(tokenizer_id).vocab_size
        return _Matcher(set(range(vocab)), vocab)


class AllowNothing:
    """Maximally incomplete: no token is ever legal."""

    name = "mock-allow-nothing"

    def compile(self, schema, tokenizer_id):
        return _Matcher(set(), load_tokenizer(tokenizer_id).vocab_size)


def test_detects_soundness_violations(candidates):
    result = check_differential(
        AllowEverything(), CASE.schema, CASE.instances[0], TOKENIZER, candidates=candidates
    )
    kinds = {v.kind for v in result.violations}
    assert "soundness" in kinds, "driver missed an engine that allows every token"


def test_detects_completeness_violations(candidates):
    result = check_differential(
        AllowNothing(), CASE.schema, CASE.instances[0], TOKENIZER, candidates=candidates
    )
    kinds = {v.kind for v in result.violations}
    assert "completeness" in kinds, "driver missed an engine that allows no token"


def test_restricted_scan_is_marked_as_not_covering_the_vocabulary(candidates):
    """A sampled scan lower-bounds the disagreement, and the result must say so."""
    partial = check_differential(
        AllowNothing(), CASE.schema, CASE.instances[0], TOKENIZER, candidates=candidates
    )
    assert partial.vocabulary_covered is False


def test_step_prefixes_are_real_prefixes_of_the_instance(candidates):
    """Regression: in byte-level BPE a multi-byte character is split across tokens.

    Concatenating each token's own text turns `{"s":"日本語"}` into `{"s":"������"}`,
    and every comparison after the first split character is then made against a string
    that appears nowhere in the language. Steps landing mid-character must be skipped,
    and the ones that are compared must use a genuine prefix.
    """
    from fuzzer.engines.xgrammar import XGrammarAdapter

    case = BY_ID["unicode_values"]
    instance = '{"s":"日本語"}'
    assert instance in case.instances
    result = check_differential(
        XGrammarAdapter(), case.schema, instance, TOKENIZER, candidates=candidates
    )
    assert result.steps, "no step was comparable"
    for step in result.steps:
        assert instance.startswith(step.prefix), f"step {step.step}: {step.prefix!r}"
        assert "�" not in step.prefix
    assert result.tokens_undecidable > 0, "the split characters should have been skipped"


def test_real_engine_agrees_on_the_baseline_case(candidates):
    """The counterpart to the mocks: no false alarms on a case known to be clean."""
    from fuzzer.engines.xgrammar import XGrammarAdapter

    result = check_differential(
        XGrammarAdapter(), CASE.schema, CASE.instances[0], TOKENIZER, candidates=candidates
    )
    assert result.violations == [], "\n".join(str(v) for v in result.violations)
    assert result.tokens_compared > 0
