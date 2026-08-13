"""Bounded token-level search for engine states that cannot reach completion."""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Literal

from fuzzer.engines.base import EngineAdapter
from fuzzer.findings import Violation
from fuzzer.oracle.reference import Reference, Unsupported
from fuzzer.tokenizers import load_tokenizer

Outcome = Literal["viable", "dead", "inconclusive"]


@dataclass
class ViabilityResult:
    lookahead_depth: int
    max_candidates: int
    max_branching: int
    steps_examined: int = 0
    candidates_checked: int = 0
    viable_candidates: int = 0
    inconclusive_candidates: int = 0
    special_tokens_skipped: int = 0
    violations: list[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations


def check_viability(
    engine: EngineAdapter,
    schema: dict,
    instance: str,
    tokenizer_id: str,
    *,
    lookahead_depth: int = 4,
    max_candidates: int = 32,
    max_branching: int = 64,
    seed: int = 0,
) -> ViabilityResult:
    """Sample allowed tokens along ``instance`` and search for engine completions.

    Search after each sampled token is exhaustive only while a state exposes at most
    ``max_branching`` ordinary tokens. Reaching the depth or branching bound is
    inconclusive, never a violation. A violation requires every reachable branch to
    terminate before the bound in a non-complete state.
    """
    if lookahead_depth < 0:
        raise ValueError("lookahead_depth must be non-negative")
    if max_candidates < 1 or max_branching < 1:
        raise ValueError("candidate and branching bounds must be positive")

    tok = load_tokenizer(tokenizer_id)
    token_ids = tok.encode(instance)
    if tok.decode(token_ids) != instance:
        raise ValueError(f"tokenization does not round-trip on {tokenizer_id}")
    special = set(tok.hf.all_special_ids)
    result = ViabilityResult(
        lookahead_depth=lookahead_depth,
        max_candidates=max_candidates,
        max_branching=max_branching,
    )
    trajectory = engine.compile(schema, tokenizer_id)
    reference = Reference(schema)

    for step in range(len(token_ids) + 1):
        allowed = trajectory.allowed_mask()
        ordinary = sorted(allowed - special)
        result.special_tokens_skipped += len(allowed & special)
        sampled = _sample(ordinary, max_candidates, seed + step)
        result.steps_examined += 1

        prefix_ids = tuple(token_ids[:step])
        for candidate in sampled:
            result.candidates_checked += 1
            outcome = _bounded_outcome(
                engine,
                schema,
                tokenizer_id,
                prefix_ids + (candidate,),
                special,
                reference,
                tok,
                lookahead_depth,
                max_branching,
            )
            if outcome == "viable":
                result.viable_candidates += 1
            elif outcome == "inconclusive":
                result.inconclusive_candidates += 1
            else:
                result.violations.append(
                    Violation(
                        kind="viability",
                        engine=engine.name,
                        tokenizer_id=tokenizer_id,
                        schema=schema,
                        instance=instance,
                        detail=(
                            "allowed token has no completion within an exhaustively "
                            f"explored depth of {lookahead_depth}"
                        ),
                        token_index=step,
                        token_id=candidate,
                        token_text=tok.decode_token(candidate),
                        context={
                            "prefix": tok.decode(list(prefix_ids)),
                            "lookahead_depth": lookahead_depth,
                            "max_branching": max_branching,
                        },
                    )
                )

        if step == len(token_ids) or not trajectory.accept(token_ids[step]):
            break

    return result


def _sample(token_ids: list[int], limit: int, seed: int) -> list[int]:
    if len(token_ids) <= limit:
        return token_ids
    return sorted(random.Random(seed).sample(token_ids, limit))


def _bounded_outcome(
    engine: EngineAdapter,
    schema: dict,
    tokenizer_id: str,
    initial_path: tuple[int, ...],
    special: set[int],
    reference: Reference,
    tok,
    lookahead_depth: int,
    max_branching: int,
) -> Outcome:
    if _guided_completion(
        engine,
        schema,
        tokenizer_id,
        initial_path,
        reference,
        tok,
        lookahead_depth,
    ):
        return "viable"

    frontier: list[tuple[tuple[int, ...], int]] = [(initial_path, 0)]
    reached_horizon = False

    while frontier:
        path, depth = frontier.pop()
        matcher = _replay(engine, schema, tokenizer_id, path)
        if matcher is None:
            continue
        if matcher.is_completed() and matcher.can_stop():
            return "viable"

        allowed = sorted(matcher.allowed_mask() - special)
        if not allowed:
            continue
        if depth >= lookahead_depth or len(allowed) > max_branching:
            reached_horizon = True
            continue
        frontier.extend((path + (token_id,), depth + 1) for token_id in allowed)

    return "inconclusive" if reached_horizon else "dead"


def _guided_completion(
    engine,
    schema,
    tokenizer_id,
    path,
    reference,
    tok,
    lookahead_depth,
):
    """Use a certified reference witness as one bounded engine path."""
    text = tok.decode(list(path))
    if "�" in text:
        return False
    try:
        verdict = reference.viable_prefix(text)
    except Unsupported:
        return False
    if not verdict or verdict.witness is None or not verdict.witness.startswith(text):
        return False

    suffix_ids = tok.encode(verdict.witness[len(text) :])
    if len(suffix_ids) > lookahead_depth:
        return False
    witness_path = path + tuple(suffix_ids)
    if tok.decode(list(witness_path)) != verdict.witness:
        return False
    matcher = _replay(engine, schema, tokenizer_id, witness_path)
    return bool(matcher and matcher.is_completed() and matcher.can_stop())


def _replay(engine, schema, tokenizer_id, path):
    matcher = engine.compile(schema, tokenizer_id)
    for token_id in path:
        if token_id not in matcher.allowed_mask() or not matcher.accept(token_id):
            return None
    return matcher
