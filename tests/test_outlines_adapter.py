"""End-to-end contract tests for the outlines-core adapter."""

from fuzzer.corpus import BY_ID
from fuzzer.engines.outlines import OutlinesAdapter
from fuzzer.oracle.validator import validate_text
from fuzzer.properties.completeness import check_completeness
from fuzzer.tokenizers import load_tokenizer

TOKENIZER = "gpt2"
CASE = BY_ID["single_string_field"]


def test_outlines_accepts_the_m0_instance_end_to_end():
    result = check_completeness(
        OutlinesAdapter(), CASE.schema, CASE.instances[0], TOKENIZER
    )
    assert result.violations == []
    assert result.tokens_checked == len(load_tokenizer(TOKENIZER).encode(CASE.instances[0]))


def test_outlines_reset_restores_the_initial_mask():
    matcher = OutlinesAdapter().compile(CASE.schema, TOKENIZER)
    initial = matcher.allowed_mask()
    token_id = load_tokenizer(TOKENIZER).encode(CASE.instances[0])[0]

    assert matcher.accept(token_id)
    assert matcher.allowed_mask() != initial
    matcher.reset()
    assert matcher.allowed_mask() == initial


def test_outlines_adapter_tracks_eos_which_core_exposes_without_a_transition():
    tok = load_tokenizer(TOKENIZER)
    matcher = OutlinesAdapter().compile(CASE.schema, TOKENIZER)
    for token_id in tok.encode(CASE.instances[0]):
        assert matcher.accept(token_id)

    assert matcher.is_completed()
    assert matcher.can_stop()
    assert not matcher.is_terminated()
    assert matcher.accept(tok.hf.eos_token_id)
    assert matcher.is_terminated()


def test_outlines_silently_accepts_an_integer_above_maximum():
    schema = {"type": "integer", "maximum": 20}
    invalid_instance = "22"
    tok = load_tokenizer(TOKENIZER)
    matcher = OutlinesAdapter().compile(schema, TOKENIZER)

    assert not validate_text(schema, invalid_instance)
    for token_id in tok.encode(invalid_instance):
        assert token_id in matcher.allowed_mask()
        assert matcher.accept(token_id)
    assert matcher.is_completed()
    assert matcher.can_stop()
