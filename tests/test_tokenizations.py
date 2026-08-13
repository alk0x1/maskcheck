"""Bounded alternate-tokenization enumeration for completeness checks."""

from fuzzer.tokenizers import load_tokenizer
from fuzzer.properties.completeness import check_completeness_variants

SCHEMA = {
    "type": "object",
    "properties": {"a": {"const": "x"}},
    "required": ["a"],
    "additionalProperties": False,
}
INSTANCE = '{"a":"x"}'


class SequenceMatcher:
    def __init__(self, sequence):
        self.sequence = tuple(sequence)
        self.path = ()

    def allowed_mask(self):
        if len(self.path) == len(self.sequence):
            return set()
        return {self.sequence[len(self.path)]}

    def accept(self, token_id):
        if token_id not in self.allowed_mask():
            return False
        self.path += (token_id,)
        return True

    def is_completed(self):
        return self.path == self.sequence

    def is_terminated(self):
        return False

    def can_stop(self):
        return self.is_completed()

    def reset(self):
        self.path = ()


class SequenceEngine:
    name = "sequence"

    def __init__(self, sequence):
        self.sequence = sequence

    def compile(self, schema, tokenizer_id):
        return SequenceMatcher(self.sequence)


def test_tokenizations_are_unique_roundtrips_with_canonical_first():
    tok = load_tokenizer("gpt2")
    text = '{"a":"x"}'
    canonical = tok.encode(text)

    tokenizations = tok.tokenizations(text, max_alternatives=8)

    assert tokenizations[0] == canonical
    assert len(tokenizations) > 1
    assert len(tokenizations) <= 9
    assert len({tuple(ids) for ids in tokenizations}) == len(tokenizations)
    assert all(tok.decode(ids) == text for ids in tokenizations)


def test_accepted_alternative_does_not_erase_canonical_rejection():
    tok = load_tokenizer("gpt2")
    canonical, alternative, *_ = tok.tokenizations(INSTANCE, max_alternatives=8)

    result = check_completeness_variants(
        SequenceEngine(alternative),
        SCHEMA,
        INSTANCE,
        "gpt2",
        max_alternatives=8,
    )

    assert result.canonical.token_ids == canonical
    assert result.canonical.violations
    assert result.any_tokenization_accepted
    assert result.canonical_failed_with_accepted_alternative
    assert len(result.alternatives) > 0
