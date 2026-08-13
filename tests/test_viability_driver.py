"""Verifier-first tests for bounded token-level viability search."""

from fuzzer.corpus import BY_ID
from fuzzer.properties.viability import check_viability
from fuzzer.tokenizers import load_tokenizer

TOKENIZER = "gpt2"
CASE = BY_ID["single_string_field"]


class StateMatcher:
    def __init__(self, transitions, completed):
        self.transitions = transitions
        self.completed = completed
        self.path = ()

    def allowed_mask(self):
        return set(self.transitions.get(self.path, {}))

    def accept(self, token_id):
        next_path = self.path + (token_id,)
        if token_id not in self.transitions.get(self.path, {}):
            return False
        self.path = next_path
        return True

    def is_completed(self):
        return self.path in self.completed

    def is_terminated(self):
        return False

    def can_stop(self):
        return self.is_completed()

    def reset(self):
        self.path = ()


class StateEngine:
    name = "mock-state-engine"

    def __init__(self, transitions, completed=()):
        self.transitions = transitions
        self.completed = set(completed)

    def compile(self, schema, tokenizer_id):
        return StateMatcher(self.transitions, self.completed)


def _token_ids():
    tok = load_tokenizer(TOKENIZER)
    canonical = tok.encode(CASE.instances[0])
    bad = tok.encode("[")[0]
    continuation = tok.encode("0")[0]
    return canonical, bad, continuation


def test_reports_a_token_that_immediately_enters_a_dead_end():
    canonical, bad, _ = _token_ids()
    good = canonical[0]
    engine = StateEngine(
        transitions={(): {good: None, bad: None}, (good,): {}},
        completed={(good,)},
    )

    result = check_viability(
        engine,
        CASE.schema,
        CASE.instances[0],
        TOKENIZER,
        lookahead_depth=4,
        max_candidates=32,
    )

    assert result.lookahead_depth == 4
    assert result.candidates_checked == 2
    assert result.viable_candidates == 1
    assert result.inconclusive_candidates == 0
    assert len(result.violations) == 1
    assert result.violations[0].kind == "viability"
    assert result.violations[0].token_id == bad


def test_horizon_exhaustion_is_inconclusive_not_a_violation():
    canonical, bad, continuation = _token_ids()
    good = canonical[0]
    engine = StateEngine(
        transitions={
            (): {good: None, bad: None},
            (good,): {},
            (bad,): {continuation: None},
            (bad, continuation): {continuation: None},
        },
        completed={(good,)},
    )

    result = check_viability(
        engine,
        CASE.schema,
        CASE.instances[0],
        TOKENIZER,
        lookahead_depth=1,
        max_candidates=32,
    )

    assert result.viable_candidates == 1
    assert result.inconclusive_candidates == 1
    assert result.violations == []


def test_reference_witness_proves_real_engine_candidates_viable():
    from fuzzer.engines.xgrammar import XGrammarAdapter

    result = check_viability(
        XGrammarAdapter(),
        CASE.schema,
        CASE.instances[0],
        TOKENIZER,
        lookahead_depth=4,
        max_candidates=8,
        max_branching=64,
    )

    assert result.viable_candidates > 0
    assert result.violations == []
