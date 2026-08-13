"""End-to-end contract tests for the llguidance adapter."""

from fuzzer.corpus import BY_ID
from fuzzer.engines.llguidance import LLGuidanceAdapter
from fuzzer.properties.completeness import check_completeness
from fuzzer.tokenizers import load_tokenizer

TOKENIZER = "gpt2"
CASE = BY_ID["single_string_field"]


def test_llguidance_accepts_the_m0_instance_end_to_end():
    result = check_completeness(
        LLGuidanceAdapter(), CASE.schema, CASE.instances[0], TOKENIZER
    )
    assert result.violations == []
    assert result.tokens_checked == len(load_tokenizer(TOKENIZER).encode(CASE.instances[0]))


def test_llguidance_reset_restores_the_initial_mask():
    matcher = LLGuidanceAdapter().compile(CASE.schema, TOKENIZER)
    initial = matcher.allowed_mask()
    token_id = load_tokenizer(TOKENIZER).encode(CASE.instances[0])[0]

    assert token_id in initial
    assert matcher.accept(token_id)
    assert matcher.allowed_mask() != initial
    matcher.reset()
    assert matcher.allowed_mask() == initial


def test_llguidance_termination_requires_consuming_eos():
    tok = load_tokenizer(TOKENIZER)
    matcher = LLGuidanceAdapter().compile(CASE.schema, TOKENIZER)
    for token_id in tok.encode(CASE.instances[0]):
        assert matcher.accept(token_id)

    assert matcher.is_completed()
    assert matcher.can_stop()
    assert not matcher.is_terminated()
    assert matcher.accept(tok.hf.eos_token_id)
    assert matcher.is_terminated()


def test_llguidance_reproduces_xgrammar_bounded_exponent_failure():
    literal = "1e1"
    bounded = {"type": "number", "minimum": 10}

    bounded_result = check_completeness(
        LLGuidanceAdapter(), bounded, literal, TOKENIZER
    )
    unbounded_result = check_completeness(
        LLGuidanceAdapter(), {"type": "number"}, literal, TOKENIZER
    )

    assert len(bounded_result.violations) == 1
    assert bounded_result.violations[0].token_text == "e"
    assert unbounded_result.violations == []
