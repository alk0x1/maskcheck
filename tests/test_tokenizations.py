"""Bounded alternate-tokenization enumeration for completeness checks."""

from fuzzer.tokenizers import Tokenizer, load_tokenizer
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


class NonRoundtripTokenizer:
    all_special_ids = []

    def __init__(self):
        self.decode_calls = 0

    def __len__(self):
        return 3

    def encode(self, text, add_special_tokens=False):
        return [2]

    def decode(self, token_ids, skip_special_tokens=False):
        self.decode_calls += 1
        return "aaaa" if token_ids == [2] else "not-a-roundtrip"


def test_alternative_search_has_an_explicit_state_budget():
    hf = NonRoundtripTokenizer()
    tok = Tokenizer("fake", hf)
    tok.__dict__["_tokens_by_initial"] = {
        "a": (("a", 0), ("a", 1)),
    }

    result = tok.enumerate_tokenizations(
        "aaaa", max_alternatives=2, max_search_states=5
    )

    assert result.tokenizations == ((2,),)
    assert result.states_examined == 5
    assert result.truncated
