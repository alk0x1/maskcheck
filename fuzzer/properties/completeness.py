"""Completeness driver.

Take a string that is valid against the schema, tokenize it the way a model actually
would, and walk the engine through those tokens. Every one of them must be legal.

This is the sharpest instrument in the project: no search, and every hit is a real bug
with a two-line reproducer. It targets boundary mismatch directly, because the
canonical tokenization is exactly where tokens straddle grammar elements.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from fuzzer.engines.base import EngineAdapter
from fuzzer.findings import Violation
from fuzzer.tokenizers import load_tokenizer


@dataclass
class CompletenessResult:
    token_ids: list[int]
    tokens_checked: int = 0
    violations: list[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


@dataclass
class MultiTokenizationResult:
    canonical: CompletenessResult
    alternatives: list[CompletenessResult]

    @property
    def all_results(self) -> list[CompletenessResult]:
        return [self.canonical, *self.alternatives]

    @property
    def any_tokenization_accepted(self) -> bool:
        return any(result.ok for result in self.all_results)

    @property
    def canonical_failed_with_accepted_alternative(self) -> bool:
        return not self.canonical.ok and any(
            result.ok for result in self.alternatives
        )

    @property
    def ok(self) -> bool:
        """Canonical rejection remains a user-impacting completeness failure."""
        return self.canonical.ok


def check_completeness(
    engine: EngineAdapter,
    schema: dict,
    instance: str,
    tokenizer_id: str,
    token_ids: list[int] | None = None,
) -> CompletenessResult:
    """Check that every token of a valid instance is accepted.

    ``instance`` must already be known valid against ``schema``; this driver does not
    re-validate, because a driver that silently tolerates an invalid fixture reports
    nothing useful. Callers pass ``token_ids`` to test a non-canonical tokenization of
    the same string.
    """
    tok = load_tokenizer(tokenizer_id)
    if token_ids is None:
        token_ids = tok.encode(instance)

    roundtrip = tok.decode(token_ids)
    if roundtrip != instance:
        # A harness bug, not an engine bug. Fail loudly rather than blame the engine
        # for rejecting tokens that spell a different string.
        raise ValueError(
            f"tokenization does not round-trip on {tokenizer_id}: "
            f"{instance!r} -> {token_ids} -> {roundtrip!r}"
        )

    def violation(detail: str, i: int | None = None, **context) -> Violation:
        return Violation(
            kind="completeness",
            engine=engine.name,
            tokenizer_id=tokenizer_id,
            schema=schema,
            instance=instance,
            detail=detail,
            token_index=i,
            token_id=None if i is None else token_ids[i],
            token_text=None if i is None else tok.decode_token(token_ids[i]),
            context={"token_ids": list(token_ids), **context},
        )

    result = CompletenessResult(token_ids=list(token_ids))
    matcher = engine.compile(schema, tokenizer_id)

    for i, token_id in enumerate(token_ids):
        if token_id not in matcher.allowed_mask():
            result.violations.append(
                violation(
                    "valid instance rejected: token not in allowed mask",
                    i,
                    prefix=tok.decode(token_ids[:i]),
                )
            )
            # State past a rejected token is undefined, so stop rather than emit a
            # cascade of derived violations from one root cause.
            return result
        if not matcher.accept(token_id):
            result.violations.append(
                violation("engine listed token as allowed but refused to accept it", i)
            )
            return result
        result.tokens_checked = i + 1

    if not matcher.is_completed():
        result.violations.append(
            violation("engine does not consider the complete valid instance a match")
        )
    elif not matcher.can_stop():
        # Distinct failure: the grammar matched but the model is never allowed to
        # emit EOS, so generation cannot terminate here.
        result.violations.append(
            violation("instance matches but no stop token is allowed; cannot terminate")
        )

    return result


def check_completeness_variants(
    engine: EngineAdapter,
    schema: dict,
    instance: str,
    tokenizer_id: str,
    *,
    max_alternatives: int = 8,
) -> MultiTokenizationResult:
    """Check canonical and bounded alternate exact-roundtrip tokenizations."""
    tok = load_tokenizer(tokenizer_id)
    tokenizations = tok.tokenizations(instance, max_alternatives=max_alternatives)
    results = [
        check_completeness(
            engine,
            schema,
            instance,
            tokenizer_id,
            token_ids=token_ids,
        )
        for token_ids in tokenizations
    ]
    return MultiTokenizationResult(canonical=results[0], alternatives=results[1:])
