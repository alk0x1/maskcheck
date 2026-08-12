"""Differential driver: engine mask against reference mask, at every step.

The completeness driver only asks whether the tokens of one valid instance are
allowed. This asks the stronger question: at each step along that instance, does the
engine allow *exactly* the tokens the reference says are viable?

Both directions are informative and they are different bugs:

- ``reference_only`` -- the reference can complete it, the engine forbids it. A
  completeness violation, and the silent kind this project exists to find.
- ``engine_only`` -- the engine allows it, no valid document has that prefix. A
  soundness violation: the model can be walked into text that cannot be repaired.

Where the reference must abstain (:class:`Unsupported`) the token is counted as
undecidable and reported, never quietly folded into agreement.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fuzzer.engines.base import EngineAdapter
from fuzzer.findings import Violation
from fuzzer.oracle.reference import Reference, Unsupported
from fuzzer.tokenizers import load_tokenizer


@dataclass
class StepDiff:
    step: int
    prefix: str
    engine_only: list[int] = field(default_factory=list)
    reference_only: list[int] = field(default_factory=list)

    @property
    def agrees(self) -> bool:
        return not self.engine_only and not self.reference_only


@dataclass
class DifferentialResult:
    steps: list[StepDiff] = field(default_factory=list)
    violations: list[Violation] = field(default_factory=list)
    tokens_compared: int = 0
    tokens_undecidable: int = 0
    vocabulary_covered: bool = True

    @property
    def ok(self) -> bool:
        return not self.violations


def check_differential(
    engine: EngineAdapter,
    schema: dict,
    instance: str,
    tokenizer_id: str,
    max_examples: int = 8,
    candidates: list[int] | None = None,
) -> DifferentialResult:
    """Compare engine and reference masks along the canonical tokenization.

    Scans the whole vocabulary by default, which is the point: a sampled scan can
    only ever lower-bound the disagreement. ``candidates`` restricts the scan, and
    the result then carries ``vocabulary_covered=False`` so a report built from it
    cannot silently claim full coverage.

    Raises :class:`Unsupported` if the reference cannot handle the schema at all;
    that is a capability gap for the caller to record, not a finding.
    """
    tok = load_tokenizer(tokenizer_id)
    reference = Reference(schema)
    texts = tok.token_texts
    token_ids = tok.encode(instance)
    scan = list(range(len(texts))) if candidates is None else list(candidates)

    result = DifferentialResult(vocabulary_covered=candidates is None)
    matcher = engine.compile(schema, tokenizer_id)
    prefix = ""

    for step, token_id in enumerate([*token_ids, None]):
        engine_allowed = matcher.allowed_mask()
        diff = StepDiff(step=step, prefix=prefix)

        for candidate in scan:
            text = texts[candidate]
            if text is None:
                result.tokens_undecidable += 1
                continue
            try:
                viable = bool(reference.viable_prefix(prefix + text))
            except Unsupported:
                result.tokens_undecidable += 1
                continue
            result.tokens_compared += 1
            in_engine = candidate in engine_allowed
            # Both directions matter and they are different bugs, so neither is
            # collapsed into the other.
            if in_engine and not viable:
                diff.engine_only.append(candidate)
            elif viable and not in_engine:
                diff.reference_only.append(candidate)

        result.steps.append(diff)
        if not diff.agrees:
            result.violations.extend(
                _violations(engine, schema, instance, tokenizer_id, tok, diff, max_examples)
            )

        if token_id is None:
            break
        if not matcher.accept(token_id):
            break
        prefix += texts[token_id] or tok.decode_token(token_id)

    return result


def _violations(engine, schema, instance, tokenizer_id, tok, diff, max_examples):
    for kind, ids, detail in (
        (
            "completeness",
            diff.reference_only,
            "engine forbids tokens the reference can complete",
        ),
        (
            "soundness",
            diff.engine_only,
            "engine allows tokens no valid document can contain",
        ),
    ):
        if not ids:
            continue
        examples = [(i, tok.decode_token(i)) for i in ids[:max_examples]]
        yield Violation(
            kind=kind,
            engine=engine.name,
            tokenizer_id=tokenizer_id,
            schema=schema,
            instance=instance,
            detail=f"{detail} after prefix {diff.prefix!r} ({len(ids)} tokens)",
            token_index=diff.step,
            context={"prefix": diff.prefix, "examples": examples, "count": len(ids)},
        )
