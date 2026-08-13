"""M3 tokenizer access, identity, and no-scaffolding contracts."""

import pytest

from fuzzer.tokenizers import REGISTRY, REVISIONS, load_tokenizer

TOKENIZERS = ("gpt2", "qwen2.5", "mistral", "llama3")


def test_m3_registers_four_structurally_distinct_tokenizers():
    assert tuple(REGISTRY) == TOKENIZERS
    assert set(REVISIONS) == set(REGISTRY)


@pytest.mark.parametrize("tokenizer_id", TOKENIZERS)
def test_tokenizer_roundtrips_json_without_special_tokens(tokenizer_id):
    tok = load_tokenizer(tokenizer_id)
    text = '{"a":"é"}'
    token_ids = tok.encode(text)

    assert token_ids
    assert not set(token_ids) & set(tok.hf.all_special_ids)
    assert tok.decode(token_ids) == text


def test_only_mistral_has_a_bos_context_mismatch_for_standalone_json():
    mismatches = {
        tokenizer_id
        for tokenizer_id in TOKENIZERS
        if load_tokenizer(tokenizer_id).has_start_context_mismatch('"a"')
    }
    assert mismatches == {"mistral"}
