"""M1 exit criterion: the reference and XGrammar agree across the handwritten suite,
or the disagreement is understood.

Every disagreement that survives is listed in KNOWN_FINDINGS with a reproducer in
findings/. A disagreement not on that list fails the suite, which is what keeps this
from degrading into a test that passes no matter what the engine does.
"""

import json

import pytest

from fuzzer.corpus import CORPUS
from fuzzer.engines.base import CompilationFailed
from fuzzer.engines.xgrammar import XGrammarAdapter
from fuzzer.oracle.validator import check_schema, validate_text
from fuzzer.properties.completeness import check_completeness

TOKENIZER = "gpt2"

# (case id, instance) -> finding file documenting why the engine rejects it.
KNOWN_FINDINGS = {
    ("integers", '{"n":-0}'): "findings/001_xgrammar_integer_negative_zero.py",
}


@pytest.fixture(scope="module")
def engine():
    return XGrammarAdapter()


@pytest.mark.parametrize("case", CORPUS, ids=lambda c: c.id)
def test_corpus_schemas_are_legal(case):
    result = check_schema(case.schema)
    assert result.valid, result.reason


@pytest.mark.parametrize("case", CORPUS, ids=lambda c: c.id)
def test_corpus_instances_are_valid(case):
    """A case whose instance is not valid tests nothing at all."""
    assert case.instances, f"{case.id} has no instances"
    for instance in case.instances:
        result = validate_text(case.schema, instance)
        assert result.valid, f"{instance!r}: {result.reason}"


@pytest.mark.parametrize("case", CORPUS, ids=lambda c: c.id)
def test_completeness_across_corpus(engine, case):
    for instance in case.instances:
        expected = KNOWN_FINDINGS.get((case.id, instance))
        try:
            result = check_completeness(engine, case.schema, instance, TOKENIZER)
        except CompilationFailed as exc:
            pytest.fail(f"{case.id}: {exc}")

        if expected:
            assert result.violations, (
                f"{case.id} {instance!r} no longer violates completeness; "
                f"{expected} may be fixed upstream, so remove it from KNOWN_FINDINGS"
            )
            continue
        assert not result.violations, "\n".join(str(v) for v in result.violations)


def test_known_findings_reference_real_files():
    """A registry entry pointing at a missing reproducer is worse than no entry."""
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent
    for key, path in KNOWN_FINDINGS.items():
        assert (root / path).is_file(), f"{key} points at missing {path}"


def test_corpus_ids_are_unique():
    ids = [c.id for c in CORPUS]
    assert len(ids) == len(set(ids))


def test_corpus_instances_are_compact_json():
    """Instances must be spelled the way a model emits them, or the tokenization
    under test is not the one that matters.

    Checked as "no whitespace outside string literals" rather than by comparing
    against ``json.dumps``, because re-serialising loses literal spellings that are
    the whole point of some cases: ``-0`` would come back as ``0``.
    """
    for case in CORPUS:
        if "whitespace" in case.tags:
            continue
        for instance in case.instances:
            assert json.loads(instance) is not None or True  # instance parses
            in_string = escaped = False
            for index, char in enumerate(instance):
                if escaped:
                    escaped = False
                elif in_string and char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = not in_string
                elif not in_string:
                    assert char not in " \t\n\r", (
                        f"{case.id}: {instance!r} has structural whitespace at {index}"
                    )
