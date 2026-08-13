"""M3 matrix aggregation and report contract."""

import json

from fuzzer.engines.base import CapabilityGap
from fuzzer.sweep import SweepConfig, generate_pairs, run_sweep
from fuzzer.oracle.validator import validate_text
from fuzzer.tokenizers import load_tokenizer

TOKENIZER = "gpt2"
SCHEMA = {
    "type": "object",
    "properties": {"a": {"const": "x"}},
    "required": ["a"],
    "additionalProperties": False,
}
INSTANCE = '{"a":"x"}'


class LiteralMatcher:
    def __init__(self, token_ids):
        self.token_ids = tuple(token_ids)
        self.path = ()

    def allowed_mask(self):
        if len(self.path) == len(self.token_ids):
            return set()
        return {self.token_ids[len(self.path)]}

    def accept(self, token_id):
        if token_id not in self.allowed_mask():
            return False
        self.path += (token_id,)
        return True

    def is_completed(self):
        return self.path == self.token_ids

    def is_terminated(self):
        return False

    def can_stop(self):
        return self.is_completed()

    def reset(self):
        self.path = ()


class LiteralEngine:
    name = "literal"

    def compile(self, schema, tokenizer_id):
        return LiteralMatcher(load_tokenizer(tokenizer_id).encode(INSTANCE))


class UnsupportedEngine:
    name = "unsupported"

    def compile(self, schema, tokenizer_id):
        raise CapabilityGap("no JSON Schema support")


def test_sweep_reports_each_property_per_engine_and_tokenizer():
    report = run_sweep(
        engines=[LiteralEngine()],
        tokenizer_ids=[TOKENIZER],
        pairs=[(SCHEMA, INSTANCE)],
        config=SweepConfig(
            soundness_walks=2,
            soundness_max_steps=8,
            viability_lookahead_depth=4,
            viability_max_candidates=8,
            viability_max_branching=16,
            completeness_max_alternatives=4,
            seed=7,
        ),
    )

    cell = report.cells[0]
    assert (cell.engine, cell.tokenizer_id) == ("literal", TOKENIZER)
    assert cell.completeness.cases_run == 1
    assert cell.completeness.alternative_checks > 0
    assert cell.soundness.cases_run == 1
    assert cell.soundness.checks_completed == 2
    assert cell.viability.cases_run == 1
    assert cell.violation_counts == {
        "completeness": 0,
        "soundness": 0,
        "viability": 0,
    }

    markdown = report.to_markdown()
    assert "literal" in markdown and "gpt2" in markdown
    assert "Viability lookahead depth | 4" in markdown
    assert "Soundness walks per schema | 2" in markdown
    assert "Completeness alternate tokenizations | 4" in markdown


def test_sweep_labels_context_sensitive_tokenizers():
    report = run_sweep(
        engines=[LiteralEngine()],
        tokenizer_ids=["mistral"],
        pairs=[(SCHEMA, INSTANCE)],
        config=SweepConfig(soundness_walks=1),
    )

    assert report.cells[0].tokenizer_context_sensitive
    assert "context-sensitive" in report.to_markdown()


def test_sweep_records_capability_gaps_instead_of_crashing():
    report = run_sweep(
        engines=[UnsupportedEngine()],
        tokenizer_ids=[TOKENIZER],
        pairs=[(SCHEMA, INSTANCE)],
        config=SweepConfig(soundness_walks=1),
    )

    cell = report.cells[0]
    assert cell.completeness.capability_gaps == 1
    assert cell.soundness.capability_gaps == 1
    assert cell.viability.capability_gaps == 1
    assert cell.all_violations == []


def test_generated_sweep_pairs_are_seeded_valid_and_repeatable():
    first = generate_pairs(count=20, max_depth=2, seed=42)
    second = generate_pairs(count=20, max_depth=2, seed=42)

    assert len(first) == 20
    assert first == second
    assert all(validate_text(schema, instance) for schema, instance in first)
