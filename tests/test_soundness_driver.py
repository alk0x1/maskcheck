"""Verifier-first tests for terminal random-walk soundness checks."""

from fuzzer.corpus import BY_ID
from fuzzer.properties.soundness import check_soundness
from fuzzer.tokenizers import load_tokenizer

TOKENIZER = "gpt2"
CASE = BY_ID["single_string_field"]


class SequenceMatcher:
    def __init__(self, sequence):
        self.sequence = tuple(sequence)
        self.path = ()

    def allowed_mask(self):
        if len(self.path) >= len(self.sequence):
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
    name = "mock-sequence-engine"

    def __init__(self, sequence):
        self.sequence = sequence

    def compile(self, schema, tokenizer_id):
        return SequenceMatcher(self.sequence)


def test_reports_completed_invalid_engine_output():
    invalid = "["
    engine = SequenceEngine(load_tokenizer(TOKENIZER).encode(invalid))

    result = check_soundness(
        engine,
        CASE.schema,
        TOKENIZER,
        walks=1,
        max_steps=8,
        seed=0,
    )

    assert result.walks_started == 1
    assert result.walks_completed == 1
    assert result.walks_inconclusive == 0
    assert len(result.violations) == 1
    assert result.violations[0].kind == "soundness"
    assert result.violations[0].instance == invalid


def test_accepts_completed_valid_engine_output():
    instance = CASE.instances[0]
    engine = SequenceEngine(load_tokenizer(TOKENIZER).encode(instance))

    result = check_soundness(
        engine,
        CASE.schema,
        TOKENIZER,
        walks=2,
        max_steps=16,
        seed=0,
    )

    assert result.walks_completed == 2
    assert result.violations == []


class OptionalInvalidExtensionMatcher:
    def __init__(self, valid_token, extension_token):
        self.valid_token = valid_token
        self.extension_token = extension_token
        self.path = ()

    def allowed_mask(self):
        if not self.path:
            return {self.valid_token}
        if self.path == (self.valid_token,):
            return {self.extension_token}
        return set()

    def accept(self, token_id):
        if token_id not in self.allowed_mask():
            return False
        self.path += (token_id,)
        return True

    def is_completed(self):
        return self.path in {
            (self.valid_token,),
            (self.valid_token, self.extension_token),
        }

    def is_terminated(self):
        return False

    def can_stop(self):
        return self.is_completed()

    def reset(self):
        self.path = ()


class OptionalInvalidExtensionEngine:
    name = "mock-optional-invalid-extension"

    def compile(self, schema, tokenizer_id):
        tok = load_tokenizer(tokenizer_id)
        return OptionalInvalidExtensionMatcher(
            tok.encode("1")[0], tok.encode("x")[0]
        )


def test_walks_continue_past_some_accepting_prefixes():
    result = check_soundness(
        OptionalInvalidExtensionEngine(),
        {"type": "integer"},
        TOKENIZER,
        walks=20,
        max_steps=2,
        seed=0,
    )

    assert result.walks_completed == 20
    assert 0 < len(result.violations) < 20
    assert {violation.instance for violation in result.violations} == {"1x"}
